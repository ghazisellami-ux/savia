#!/bin/bash
# ==========================================
# 🚀 SAVIA Deployment Script
# Déploie l'application depuis GitHub sur le VPS
# ==========================================

set -e  # Exit on error

VPS_USER="ubuntu"
VPS_IP="51.91.124.49"
VPS_PATH="/home/ubuntu/savia"
GITHUB_REPO="https://github.com/ghazisellami-ux/savia.git"
BRANCH="develop"

echo "=========================================="
echo "🚀 SAVIA Deployment Script"
echo "=========================================="
echo ""
echo "VPS: $VPS_USER@$VPS_IP"
echo "Path: $VPS_PATH"
echo "Branch: $BRANCH"
echo ""

# ==========================================
# 1. SSH Connection Test
# ==========================================
echo "1️⃣  Testing SSH connection..."
if ssh -o ConnectTimeout=5 $VPS_USER@$VPS_IP "echo 'SSH OK'" > /dev/null 2>&1; then
    echo "✅ SSH connection OK"
else
    echo "❌ SSH connection failed"
    exit 1
fi

# ==========================================
# 2. Clone or Update Repository
# ==========================================
echo ""
echo "2️⃣  Updating repository..."
ssh $VPS_USER@$VPS_IP << 'EOF'
    cd /home/ubuntu
    
    if [ -d "savia" ]; then
        echo "Repository exists, pulling latest changes..."
        cd savia
        git fetch origin
        git checkout develop
        git pull origin develop
    else
        echo "Cloning repository..."
        git clone -b develop $GITHUB_REPO savia
        cd savia
    fi
    
    echo "✅ Repository updated"
EOF

# ==========================================
# 3. Check .env file
# ==========================================
echo ""
echo "3️⃣  Checking .env file..."
ssh $VPS_USER@$VPS_IP << 'EOF'
    if [ ! -f "$VPS_PATH/.env" ]; then
        echo "⚠️  .env file not found!"
        echo "Creating .env from .env.example..."
        cp $VPS_PATH/.env.example $VPS_PATH/.env
        echo "⚠️  Please edit .env with your configuration:"
        echo "   nano $VPS_PATH/.env"
        exit 1
    else
        echo "✅ .env file exists"
    fi
EOF

# ==========================================
# 4. Stop existing containers
# ==========================================
echo ""
echo "4️⃣  Stopping existing containers..."
ssh $VPS_USER@$VPS_IP << 'EOF'
    cd $VPS_PATH
    docker-compose down || true
    echo "✅ Containers stopped"
EOF

# ==========================================
# 5. Build Docker images
# ==========================================
echo ""
echo "5️⃣  Building Docker images..."
ssh $VPS_USER@$VPS_IP << 'EOF'
    cd $VPS_PATH
    docker-compose build --no-cache
    echo "✅ Docker images built"
EOF

# ==========================================
# 6. Start services
# ==========================================
echo ""
echo "6️⃣  Starting services..."
ssh $VPS_USER@$VPS_IP << 'EOF'
    cd $VPS_PATH
    docker-compose up -d
    echo "✅ Services started"
EOF

# ==========================================
# 7. Wait for services to be ready
# ==========================================
echo ""
echo "7️⃣  Waiting for services to be ready..."
sleep 10

# ==========================================
# 8. Check service status
# ==========================================
echo ""
echo "8️⃣  Checking service status..."
ssh $VPS_USER@$VPS_IP << 'EOF'
    cd $VPS_PATH
    echo ""
    echo "Service Status:"
    docker-compose ps
    echo ""
    echo "Recent logs:"
    docker-compose logs --tail=20
EOF

# ==========================================
# 9. Verify deployment
# ==========================================
echo ""
echo "9️⃣  Verifying deployment..."
ssh $VPS_USER@$VPS_IP << 'EOF'
    echo ""
    echo "Checking backend health..."
    if curl -s http://localhost:8001/docs > /dev/null; then
        echo "✅ Backend is running"
    else
        echo "⚠️  Backend might not be ready yet"
    fi
    
    echo ""
    echo "Checking frontend..."
    if curl -s http://localhost:3000 > /dev/null; then
        echo "✅ Frontend is running"
    else
        echo "⚠️  Frontend might not be ready yet"
    fi
EOF

# ==========================================
# Summary
# ==========================================
echo ""
echo "=========================================="
echo "✅ Deployment Complete!"
echo "=========================================="
echo ""
echo "📍 Application URLs:"
echo "   Frontend: http://51.91.124.49:3000"
echo "   Backend API: http://51.91.124.49:8001"
echo "   API Docs: http://51.91.124.49:8001/docs"
echo ""
echo "📝 Useful commands:"
echo "   View logs:     ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose logs -f'"
echo "   Stop services: ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose down'"
echo "   Restart:       ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose restart'"
echo ""
echo "=========================================="
