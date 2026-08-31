@echo off
REM ============================================================
REM  FinalGrid — Cloudflare Tunnel Starter
REM  Double-click this file to start the internet tunnel.
REM  Keep this window open while the hotel is operating.
REM ============================================================

echo.
echo  ====================================
echo    FinalGrid
echo    Starting Cloudflare Tunnel...
echo  ====================================
echo.
echo  Your PMS will be accessible at:
echo    https://pms.yourdomain.com
echo    https://book.yourdomain.com  (public booking)
echo.
echo  Do NOT close this window.
echo  Press Ctrl+C to stop the tunnel.
echo.

REM Path to cloudflared — update if installed elsewhere
cloudflared tunnel --config "%~dp0config.yml" run

pause
