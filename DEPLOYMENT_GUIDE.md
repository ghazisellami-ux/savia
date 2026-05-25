# 🚀 SAVIA Deployment Guide

## VPS Information
- **Host**: 51.91.124.49
- **User**: ubuntu
- **Path**: /home/ubuntu/savia
- **Repository**: https://github.com/ghazisellami-ux/savia.git
- **Branch**: develop

---

## 📋 Prerequisites

### On your local machine:
- SSH client (built-in on Linux/Mac, or Git Bash on Windows)
- PowerShell (for Windows deployment script)
- Git installed

### On the VPS:
- Docker installed
- Docker Compose installed
- Git installed
- SSH access configured

---

## 🚀 Quick Deployment (Recommended)

### Option 1: Using PowerShell (Windows)

```powershell
# Navigate to project directory
cd C:\Users\ACER\Desktop\savia-next

# Run deployment script
powershell -ExecutionPolicy Bypass -File deploy.ps1
```

### Option 2: Using Bash (Linux/Mac)

```bash
# Navigate to project directory
cd /path/to/savia-next

# Make script executable
chmod +x deploy.sh

# Run deployment script
./deploy.sh
```

### Option 3: Manual SSH Commands

```bash
# 1. Connect to VPS
ssh ubuntu@51.91.124.49

# 2. Navigate to app directory
cd /home/ubuntu/savia

# 3. Pull latest code
git fetch origin
git checkout develop
git pull origin develop

# 4. Stop existing containers
docker-compose down

# 5. Build images
docker-compose build --no-cache

# 6. Start services
docker-compose up -d

# 7. Check status
docker-compose ps
docker-compose logs -f
```

---

## 🔧 Configuration

### First Time Setup

1. **SSH into VPS**:
   ```bash
   ssh ubuntu@51.91.124.49
   ```

2. **Create .env file**:
   ```bash
   cd /home/ubuntu/savia
   cp .env.example .env
   nano .env
   ```

3. **Edit .env with your values**:
   ```env
   # Database
   POSTGRES_DB=savia_db
   POSTGRES_USER=savia_user
   POSTGRES_PASSWORD=your_secure_password
   DATABASE_URL=postgresql://savia_user:your_secure_password@postgres:5432/savia_db

   # JWT
   JWT_SECRET=your_jwt_secret_key

   # S3/MinIO
   MINIO_ROOT_USER=minioadmin
   MINIO_ROOT_PASSWORD=minioadmin
   S3_BUCKET=savia-logs

   # API URLs
   BACKEND_URL=http://backend:8001
   NEXT_PUBLIC_API_URL=https://your-domain.com/api

   # Telegram (optional)
   TELEGRAM_TOKEN=your_token
   TELEGRAM_CHAT_ID=your_chat_id
   ```

4. **Save and exit** (Ctrl+X, then Y, then Enter)

---

## 📊 Monitoring & Management

### View Logs

```bash
# All services
ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose logs -f'

# Specific service
ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose logs -f backend'
ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose logs -f frontend'
ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose logs -f postgres'
```

### Check Service Status

```bash
ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose ps'
```

### Restart Services

```bash
# Restart all
ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose restart'

# Restart specific service
ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose restart backend'
```

### Stop Services

```bash
ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose down'
```

### View Resource Usage

```bash
ssh ubuntu@51.91.124.49 'docker stats'
```

---

## 🔄 Update Deployment

To deploy new changes from GitHub:

```bash
# Option 1: Using script
powershell -ExecutionPolicy Bypass -File deploy.ps1

# Option 2: Manual
ssh ubuntu@51.91.124.49 << 'EOF'
cd /home/ubuntu/savia
git pull origin develop
docker-compose up -d --build
EOF
```

---

## 🐛 Troubleshooting

### Services won't start

```bash
# Check logs
ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose logs'

# Rebuild images
ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose build --no-cache'

# Restart
ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose up -d'
```

### Database connection error

```bash
# Check if postgres is running
ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose ps postgres'

# Check postgres logs
ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose logs postgres'

# Verify .env DATABASE_URL
ssh ubuntu@51.91.124.49 'cat /home/ubuntu/savia/.env | grep DATABASE_URL'
```

### Backend API not responding

```bash
# Check backend logs
ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose logs backend'

# Test backend health
ssh ubuntu@51.91.124.49 'curl http://localhost:8001/docs'

# Restart backend
ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose restart backend'
```

### Frontend not loading

```bash
# Check frontend logs
ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose logs frontend'

# Test frontend
ssh ubuntu@51.91.124.49 'curl http://localhost:3000'

# Rebuild frontend
ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose build --no-cache frontend'
```

---

## 📦 Backup & Restore

### Backup Database

```bash
ssh ubuntu@51.91.124.49 << 'EOF'
cd /home/ubuntu/savia
docker-compose exec postgres pg_dump -U savia_user savia_db > backup_$(date +%Y%m%d_%H%M%S).sql
EOF
```

### Restore Database

```bash
ssh ubuntu@51.91.124.49 << 'EOF'
cd /home/ubuntu/savia
docker-compose exec -T postgres psql -U savia_user savia_db < backup_20240101_120000.sql
EOF
```

---

## 🌐 Access Application

After deployment:

- **Frontend**: http://51.91.124.49:3000
- **Backend API**: http://51.91.124.49:8001
- **API Documentation**: http://51.91.124.49:8001/docs
- **Database**: postgres://savia_user@localhost:5432/savia_db

---

## 📝 Useful Docker Commands

```bash
# SSH into container
ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose exec backend bash'

# Run command in container
ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose exec backend python -c "print(\"Hello\")"'

# View container details
ssh ubuntu@51.91.124.49 'docker inspect savia_backend'

# Clean up unused images
ssh ubuntu@51.91.124.49 'docker system prune -a'
```

---

## ✅ Deployment Checklist

- [ ] SSH access to VPS working
- [ ] Git repository cloned/updated
- [ ] .env file configured
- [ ] Docker images built successfully
- [ ] All services running (`docker-compose ps`)
- [ ] Backend API responding (`curl http://localhost:8001/docs`)
- [ ] Frontend accessible (`curl http://localhost:3000`)
- [ ] Database initialized
- [ ] Logs checked for errors

---

## 🆘 Support

For issues or questions:
1. Check logs: `docker-compose logs -f`
2. Verify .env configuration
3. Ensure all services are running: `docker-compose ps`
4. Check VPS resources: `docker stats`

---

**Last Updated**: May 21, 2026
**Version**: 2.0.0
