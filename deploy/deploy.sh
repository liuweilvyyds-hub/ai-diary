#!/bin/bash
# AI Diary - Alibaba Cloud Linux 3 Deployment Script
# Run as root or with sudo

set -e

APP_NAME="ai-diary"
APP_DIR="/opt/$APP_NAME"
APP_USER="$APP_NAME"
APP_PORT=8000
DOMAIN="liuweiyyds.com"

echo "=== AI Diary Deployment ==="
echo "Domain: $DOMAIN"
echo "Port: $APP_PORT"

# ---------- 1. System packages ----------
echo "[1/7] Installing system packages..."
yum install -y python3 python3-pip nginx git

# ---------- 2. Create app user ----------
echo "[2/7] Creating app user..."
id -u "$APP_USER" &>/dev/null || useradd -r -s /sbin/nologin "$APP_USER"

# ---------- 3. Install app ----------
echo "[3/7] Installing application..."
mkdir -p "$APP_DIR"
# Copy files (run from project root)
cp -r . "$APP_DIR/"
cd "$APP_DIR"

# Install Python dependencies
pip3 install --upgrade pip
pip3 install -r requirements.txt

# Create upload directory
mkdir -p static/uploads
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# ---------- 4. Create systemd service ----------
echo "[4/7] Creating systemd service..."
cat > /etc/systemd/system/$APP_NAME.service << EOF
[Unit]
Description=AI Diary FastAPI Application
After=network.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=/usr/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port $APP_PORT --workers 2
Restart=always
RestartSec=5
StandardOutput=append:$APP_DIR/server.log
StandardError=append:$APP_DIR/server_err.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable $APP_NAME
systemctl start $APP_NAME

# ---------- 5. Configure Nginx ----------
echo "[5/7] Configuring Nginx..."
cat > /etc/nginx/conf.d/$APP_NAME.conf << EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    # Static files
    location /static/ {
        alias $APP_DIR/static/;
        expires 7d;
        add_header Cache-Control "public, no-transform";
    }

    # API proxy
    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 10s;
    }

    # Upload size limit
    client_max_body_size 20M;
}
EOF

# Test and reload Nginx
nginx -t
systemctl enable nginx
systemctl reload nginx

# ---------- 6. Firewall ----------
echo "[6/7] Configuring firewall..."
# Alibaba Cloud uses security groups, not firewalld by default
# But just in case:
if command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-service=http 2>/dev/null || true
    firewall-cmd --permanent --add-service=https 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
fi

# ---------- 7. Status ----------
echo "[7/7] Checking status..."
sleep 2
echo ""
echo "=== Deployment Complete ==="
echo "App status: $(systemctl is-active $APP_NAME)"
echo "Nginx status: $(systemctl is-active nginx)"
echo ""
echo "Access your app at:"
echo "  http://$DOMAIN"
echo "  http://$(curl -s ifconfig.me)"
echo ""
echo "Next steps:"
echo "  1. Set DEEPSEEK_API_KEY in $APP_DIR/.env"
echo "  2. Configure DNS A record: $DOMAIN -> $(curl -s ifconfig.me)"
echo "  3. (Optional) Install certbot for HTTPS: yum install -y certbot python3-certbot-nginx"
echo "  4. (Optional) Run: certbot --nginx -d $DOMAIN"
