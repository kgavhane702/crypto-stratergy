from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional, Set
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

from .config import get_settings
from .utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Trade:
    id: str
    symbol: str
    side: str
    entry_time: str
    entry_price: float
    sl_price: float
    quantity: float
    trend_aligned: bool
    status: str  # "OPEN", "CLOSED", "SL_HIT", "TARGET_HIT"
    exit_time: Optional[str] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    current_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None


@dataclass
class ZoneInfo:
    symbol: str
    high_close: float
    low_close: float
    width: float
    touches_top: int
    touches_bottom: int
    dwell_bars: int
    priority_score: float
    last_updated: str


@dataclass
class DashboardState:
    trades: List[Trade]
    zones: List[ZoneInfo]
    stats: Dict
    system_info: Dict[str, Any]  # Global scanner and monitor pool info
    last_update: str


class Dashboard:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.trades: Dict[str, Trade] = {}
        self.zones: Dict[str, ZoneInfo] = {}
        self.stats = {
            "total_trades": 0,
            "open_trades": 0,
            "closed_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
        }
        self.system_info = {
            "global_scanner_status": "STOPPED",
            "monitor_pool_size": 0,
            "priority_pool_size": 0,
            "total_symbols_scanned": 0,
            "last_scan_time": "",
            "active_zones_count": 0,
            "candidates_in_queue": 0,
        }
        self.lock = threading.Lock()
        self.server: Optional[HTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None

    def add_trade(self, trade: Trade) -> None:
        """Add a new trade to the dashboard."""
        with self.lock:
            self.trades[trade.id] = trade
            self._update_stats()

    def update_trade(self, trade_id: str, **kwargs) -> None:
        """Update an existing trade."""
        with self.lock:
            if trade_id in self.trades:
                for key, value in kwargs.items():
                    if hasattr(self.trades[trade_id], key):
                        setattr(self.trades[trade_id], key, value)
                self._update_stats()

    def add_zone(self, zone: ZoneInfo) -> None:
        """Add or update a zone."""
        with self.lock:
            self.zones[zone.symbol] = zone

    def remove_zone(self, symbol: str) -> None:
        """Remove a zone."""
        with self.lock:
            self.zones.pop(symbol, None)

    def _update_stats(self) -> None:
        """Update dashboard statistics."""
        closed_trades = [t for t in self.trades.values() if t.status == "CLOSED"]
        open_trades = [t for t in self.trades.values() if t.status == "OPEN"]
        
        self.stats["total_trades"] = len(self.trades)
        self.stats["open_trades"] = len(open_trades)
        self.stats["closed_trades"] = len(closed_trades)
        
        if closed_trades:
            winning_trades = [t for t in closed_trades if t.pnl and t.pnl > 0]
            losing_trades = [t for t in closed_trades if t.pnl and t.pnl < 0]
            
            self.stats["winning_trades"] = len(winning_trades)
            self.stats["losing_trades"] = len(losing_trades)
            self.stats["win_rate"] = len(winning_trades) / len(closed_trades) * 100
            
            total_pnl = sum(t.pnl for t in closed_trades if t.pnl)
            self.stats["total_pnl"] = total_pnl
            
            if winning_trades:
                self.stats["avg_win"] = sum(t.pnl for t in winning_trades if t.pnl) / len(winning_trades)
            if losing_trades:
                self.stats["avg_loss"] = sum(t.pnl for t in losing_trades if t.pnl) / len(losing_trades)

    def get_state(self) -> DashboardState:
        """Get current dashboard state."""
        with self.lock:
            return DashboardState(
                trades=list(self.trades.values()),
                zones=list(self.zones.values()),
                stats=self.stats.copy(),
                system_info=self.system_info.copy(),
                last_update=datetime.now().isoformat()
            )

    def update_system_info(self, **kwargs) -> None:
        """Update system information."""
        with self.lock:
            for key, value in kwargs.items():
                if key in self.system_info:
                    self.system_info[key] = value

    def start(self) -> None:
        """Start the dashboard server."""
        if self.server_thread and self.server_thread.is_alive():
            return
        
        self.server_thread = threading.Thread(target=self._run_server, daemon=True)
        self.server_thread.start()
        logger.info(f"Dashboard started on port {self.settings.dashboard_port}")

    def _run_server(self) -> None:
        """Run the HTTP server."""
        class DashboardHandler(BaseHTTPRequestHandler):
            dashboard = self
            
            def do_GET(self):
                parsed_path = urllib.parse.urlparse(self.path)
                path = parsed_path.path
                
                if path == "/":
                    self._serve_dashboard()
                elif path == "/api/state":
                    self._serve_api_state()
                elif path == "/api/trades":
                    self._serve_api_trades()
                elif path == "/api/zones":
                    self._serve_api_zones()
                elif path == "/api/stats":
                    self._serve_api_stats()
                else:
                    self.send_error(404)
            
            def _serve_dashboard(self):
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(self._get_dashboard_html().encode())
            
            def _serve_api_state(self):
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                state = self.dashboard.get_state()
                self.wfile.write(json.dumps(asdict(state)).encode())
            
            def _serve_api_trades(self):
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                trades = [asdict(t) for t in self.dashboard.trades.values()]
                self.wfile.write(json.dumps(trades).encode())
            
            def _serve_api_zones(self):
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                zones = [asdict(z) for z in self.dashboard.zones.values()]
                self.wfile.write(json.dumps(zones).encode())
            
            def _serve_api_stats(self):
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(self.dashboard.stats).encode())
            
            def _get_dashboard_html(self) -> str:
                return DASHBOARD_HTML
            
            def log_message(self, format, *args):
                # Suppress HTTP server logs
                pass
        
        try:
            self.server = HTTPServer(("", self.settings.dashboard_port), DashboardHandler)
            self.server.serve_forever()
        except Exception as e:
            logger.error(f"Dashboard server error: {e}")

    def stop(self) -> None:
        """Stop the dashboard server."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()


# Global dashboard instance
dashboard = Dashboard()


# HTML Dashboard Template
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MTF Breakout Strategy Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: #333;
            min-height: 100vh;
        }
        
        .container {
            max-width: 1600px;
            margin: 0 auto;
            padding: 20px;
        }
        
        /* Navigation Menu */
        .nav-menu {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 15px 20px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        }
        
        .nav-menu ul {
            list-style: none;
            display: flex;
            justify-content: center;
            gap: 30px;
        }
        
        .nav-menu li {
            position: relative;
        }
        
        .nav-menu a {
            text-decoration: none;
            color: #1e3c72;
            font-weight: 600;
            padding: 10px 15px;
            border-radius: 8px;
            transition: all 0.3s ease;
            display: block;
        }
        
        .nav-menu a:hover {
            background: #1e3c72;
            color: white;
        }
        
        .nav-menu a.active {
            background: #1e3c72;
            color: white;
        }
        
        /* System Status Bar */
        .system-status {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        }
        
        .system-status h2 {
            color: #1e3c72;
            margin-bottom: 15px;
            text-align: center;
        }
        
        .status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }
        
        .status-item {
            background: white;
            border-radius: 10px;
            padding: 15px;
            text-align: center;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
        }
        
        .status-item h4 {
            color: #666;
            font-size: 12px;
            margin-bottom: 5px;
            text-transform: uppercase;
        }
        
        .status-item .value {
            font-size: 20px;
            font-weight: bold;
            color: #1e3c72;
        }
        
        .status-item .status-running { color: #28a745; }
        .status-item .status-stopped { color: #dc3545; }
        .status-item .status-warning { color: #ffc107; }
        
        .header {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        }
        
        .header h1 {
            color: #1e3c72;
            text-align: center;
            margin-bottom: 10px;
        }
        
        .status-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(255, 255, 255, 0.9);
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
        }
        
        .stat-card {
            background: white;
            border-radius: 10px;
            padding: 15px;
            text-align: center;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
            flex: 1;
            margin: 0 10px;
        }
        
        .stat-card h3 {
            color: #666;
            font-size: 14px;
            margin-bottom: 5px;
        }
        
        .stat-card .value {
            font-size: 24px;
            font-weight: bold;
            color: #1e3c72;
        }
        
        .stat-card .positive { color: #28a745; }
        .stat-card .negative { color: #dc3545; }
        
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .card {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        }
        
        .card h2 {
            color: #1e3c72;
            margin-bottom: 15px;
            border-bottom: 2px solid #e9ecef;
            padding-bottom: 10px;
        }
        
        .trades-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }
        
        .trades-table th,
        .trades-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e9ecef;
        }
        
        .trades-table th {
            background: #f8f9fa;
            font-weight: 600;
            color: #495057;
        }
        
        .trades-table tr:hover {
            background: #f8f9fa;
        }
        
        .status-open { color: #007bff; font-weight: bold; }
        .status-closed { color: #28a745; font-weight: bold; }
        .status-sl { color: #dc3545; font-weight: bold; }
        
        .side-long { color: #28a745; font-weight: bold; }
        .side-short { color: #dc3545; font-weight: bold; }
        
        .zones-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 15px;
        }
        
        .zone-card {
            background: white;
            border-radius: 10px;
            padding: 15px;
            border-left: 4px solid #007bff;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }
        
        .zone-card h4 {
            color: #1e3c72;
            margin-bottom: 10px;
        }
        
        .zone-stats {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            font-size: 14px;
        }
        
        .zone-stat {
            display: flex;
            justify-content: space-between;
        }
        
        .refresh-btn {
            background: #007bff;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
        }
        
        .refresh-btn:hover {
            background: #0056b3;
        }
        
        .auto-refresh {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .auto-refresh input[type="checkbox"] {
            transform: scale(1.2);
        }
        
        @media (max-width: 768px) {
            .grid {
                grid-template-columns: 1fr;
            }
            
            .status-bar {
                flex-direction: column;
                gap: 10px;
            }
            
            .stat-card {
                margin: 5px 0;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Navigation Menu -->
        <div class="nav-menu">
            <ul>
                <li><a href="#" class="active" onclick="showSection('overview')">📊 Overview</a></li>
                <li><a href="#" onclick="showSection('trades')">💰 Trades</a></li>
                <li><a href="#" onclick="showSection('zones')">🎯 Zones</a></li>
                <li><a href="#" onclick="showSection('system')">⚙️ System</a></li>
                <li><a href="#" onclick="showSection('stats')">📈 Statistics</a></li>
            </ul>
        </div>

        <!-- System Status Bar -->
        <div class="system-status">
            <h2>🖥️ System Status</h2>
            <div class="status-grid">
                <div class="status-item">
                    <h4>Global Scanner</h4>
                    <div id="scannerStatus" class="value status-stopped">STOPPED</div>
                </div>
                <div class="status-item">
                    <h4>Monitor Pool</h4>
                    <div id="monitorPoolSize" class="value">0</div>
                </div>
                <div class="status-item">
                    <h4>Priority Pool</h4>
                    <div id="priorityPoolSize" class="value">0</div>
                </div>
                <div class="status-item">
                    <h4>Active Zones</h4>
                    <div id="activeZonesCount" class="value">0</div>
                </div>
                <div class="status-item">
                    <h4>Symbols Scanned</h4>
                    <div id="symbolsScanned" class="value">0</div>
                </div>
                <div class="status-item">
                    <h4>Last Scan</h4>
                    <div id="lastScanTime" class="value">-</div>
                </div>
            </div>
        </div>

        <!-- Overview Section -->
        <div id="overview-section" class="section">
            <div class="header">
                <h1>🚀 MTF Breakout Strategy Dashboard</h1>
                <p style="text-align: center; color: #666;">Real-time monitoring and performance tracking</p>
            </div>
            
            <div class="status-bar">
                <div class="auto-refresh">
                    <input type="checkbox" id="autoRefresh" checked>
                    <label for="autoRefresh">Auto-refresh (5s)</label>
                </div>
                <button class="refresh-btn" onclick="refreshData()">🔄 Refresh Now</button>
                <div id="lastUpdate" style="color: #666; font-size: 14px;"></div>
            </div>
            
            <div class="status-bar">
                <div class="stat-card">
                    <h3>Total P&L</h3>
                    <div id="totalPnl" class="value">$0.00</div>
                </div>
                <div class="stat-card">
                    <h3>Win Rate</h3>
                    <div id="winRate" class="value">0%</div>
                </div>
                <div class="stat-card">
                    <h3>Open Trades</h3>
                    <div id="openTrades" class="value">0</div>
                </div>
                <div class="stat-card">
                    <h3>Total Trades</h3>
                    <div id="totalTrades" class="value">0</div>
                </div>
            </div>
            
            <div class="grid">
                <div class="card">
                    <h2>📊 Recent Trades</h2>
                    <div id="recentTradesTable"></div>
                </div>
                
                <div class="card">
                    <h2>🎯 Active Zones</h2>
                    <div id="activeZonesGrid" class="zones-grid"></div>
                </div>
            </div>
        </div>

        <!-- Trades Section -->
        <div id="trades-section" class="section" style="display: none;">
            <div class="card">
                <h2>💰 All Trades</h2>
                <div id="allTradesTable"></div>
            </div>
        </div>

        <!-- Zones Section -->
        <div id="zones-section" class="section" style="display: none;">
            <div class="card">
                <h2>🎯 All Monitor Zones</h2>
                <div id="allZonesGrid" class="zones-grid"></div>
            </div>
        </div>

        <!-- System Section -->
        <div id="system-section" class="section" style="display: none;">
            <div class="card">
                <h2>⚙️ System Information</h2>
                <div id="systemInfo"></div>
            </div>
        </div>

        <!-- Statistics Section -->
        <div id="stats-section" class="section" style="display: none;">
            <div class="card">
                <h2>📈 Performance Statistics</h2>
                <div id="performanceStats"></div>
            </div>
        </div>
    </div>

    <script>
        let autoRefreshInterval;
        
        function startAutoRefresh() {
            if (autoRefreshInterval) {
                clearInterval(autoRefreshInterval);
            }
            autoRefreshInterval = setInterval(refreshData, 5000);
        }
        
        function stopAutoRefresh() {
            if (autoRefreshInterval) {
                clearInterval(autoRefreshInterval);
                autoRefreshInterval = null;
            }
        }
        
        document.getElementById('autoRefresh').addEventListener('change', function(e) {
            if (e.target.checked) {
                startAutoRefresh();
            } else {
                stopAutoRefresh();
            }
        });
        
        async function refreshData() {
            try {
                const response = await fetch('/api/state');
                const data = await response.json();
                updateDashboard(data);
            } catch (error) {
                console.error('Error fetching data:', error);
            }
        }
        
        function updateDashboard(data) {
            // Update stats
            document.getElementById('totalPnl').textContent = formatCurrency(data.stats.total_pnl);
            document.getElementById('totalPnl').className = 'value ' + (data.stats.total_pnl >= 0 ? 'positive' : 'negative');
            document.getElementById('winRate').textContent = data.stats.win_rate.toFixed(1) + '%';
            document.getElementById('openTrades').textContent = data.stats.open_trades;
            document.getElementById('totalTrades').textContent = data.stats.total_trades;
            
            // Update system information
            updateSystemInfo(data.system_info);
            
            // Update last update time
            document.getElementById('lastUpdate').textContent = 'Last update: ' + new Date().toLocaleTimeString();
            
            // Update trades table
            updateTradesTable(data.trades);
            
            // Update zones grid
            updateZonesGrid(data.zones);
        }

        function updateSystemInfo(systemInfo) {
            // Update system status
            const scannerStatus = document.getElementById('scannerStatus');
            scannerStatus.textContent = systemInfo.global_scanner_status;
            scannerStatus.className = 'value status-' + systemInfo.global_scanner_status.toLowerCase();
            
            document.getElementById('monitorPoolSize').textContent = systemInfo.monitor_pool_size;
            document.getElementById('priorityPoolSize').textContent = systemInfo.priority_pool_size;
            document.getElementById('activeZonesCount').textContent = systemInfo.active_zones_count;
            document.getElementById('symbolsScanned').textContent = systemInfo.total_symbols_scanned;
            document.getElementById('lastScanTime').textContent = systemInfo.last_scan_time || '-';
        }

        function showSection(sectionName) {
            // Hide all sections
            document.querySelectorAll('.section').forEach(section => {
                section.style.display = 'none';
            });
            
            // Show selected section
            document.getElementById(sectionName + '-section').style.display = 'block';
            
            // Update navigation
            document.querySelectorAll('.nav-menu a').forEach(link => {
                link.classList.remove('active');
            });
            event.target.classList.add('active');
        }
        
        function updateTradesTable(trades) {
            const container = document.getElementById('tradesTable');
            
            if (trades.length === 0) {
                container.innerHTML = '<p style="text-align: center; color: #666; padding: 20px;">No active trades</p>';
                return;
            }
            
            let html = `
                <table class="trades-table">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Side</th>
                            <th>Entry Price</th>
                            <th>Current/SL</th>
                            <th>P&L</th>
                            <th>Status</th>
                            <th>Time</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            
            trades.forEach(trade => {
                const pnl = trade.pnl || trade.unrealized_pnl || 0;
                const pnlClass = pnl >= 0 ? 'positive' : 'negative';
                const statusClass = 'status-' + trade.status.toLowerCase();
                
                html += `
                    <tr>
                        <td><strong>${trade.symbol}</strong></td>
                        <td class="side-${trade.side.toLowerCase()}">${trade.side}</td>
                        <td>$${trade.entry_price.toFixed(2)}</td>
                        <td>$${trade.current_price ? trade.current_price.toFixed(2) : trade.sl_price.toFixed(2)}</td>
                        <td class="${pnlClass}">${formatCurrency(pnl)}</td>
                        <td class="${statusClass}">${trade.status}</td>
                        <td>${formatTime(trade.entry_time)}</td>
                    </tr>
                `;
            });
            
            html += '</tbody></table>';
            container.innerHTML = html;
        }
        
        function updateZonesGrid(zones) {
            const container = document.getElementById('zonesGrid');
            
            if (zones.length === 0) {
                container.innerHTML = '<p style="text-align: center; color: #666; padding: 20px;">No active zones</p>';
                return;
            }
            
            let html = '';
            zones.forEach(zone => {
                html += `
                    <div class="zone-card">
                        <h4>${zone.symbol}</h4>
                        <div class="zone-stats">
                            <div class="zone-stat">
                                <span>High:</span>
                                <span>$${zone.high_close.toFixed(2)}</span>
                            </div>
                            <div class="zone-stat">
                                <span>Low:</span>
                                <span>$${zone.low_close.toFixed(2)}</span>
                            </div>
                            <div class="zone-stat">
                                <span>Width:</span>
                                <span>$${zone.width.toFixed(2)}</span>
                            </div>
                            <div class="zone-stat">
                                <span>Dwell:</span>
                                <span>${zone.dwell_bars} bars</span>
                            </div>
                            <div class="zone-stat">
                                <span>Touches Top:</span>
                                <span>${zone.touches_top}</span>
                            </div>
                            <div class="zone-stat">
                                <span>Touches Bottom:</span>
                                <span>${zone.touches_bottom}</span>
                            </div>
                            <div class="zone-stat">
                                <span>Priority:</span>
                                <span>${zone.priority_score.toFixed(2)}</span>
                            </div>
                        </div>
                    </div>
                `;
            });
            
            container.innerHTML = html;
        }
        
        function formatCurrency(amount) {
            return new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD',
                minimumFractionDigits: 2
            }).format(amount);
        }
        
        function formatTime(timeStr) {
            return new Date(timeStr).toLocaleTimeString();
        }
        
        // Initial load
        refreshData();
        startAutoRefresh();
    </script>
</body>
</html>
"""
