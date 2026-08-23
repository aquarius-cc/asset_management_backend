# 资产管理系统后端部署文档 (DEPLOYMENT.md)

> 适用：Python 3.12+ / Django 6.0 / DRF 3.15+  
> 目标环境：Ubuntu 22.04 LTS + PostgreSQL 16  
> 遵循：`AGENTS.md`、`SECURITY.md`、`API_STANDARDS.md`

---

## 1. 基础环境

| 资源  | 最低要求             |
| --- | ---------------- |
| OS  | Ubuntu 22.04 LTS |
| CPU | 2 核+             |
| 内存  | 4 GB+            |
| 磁盘  | 40 GB+ (SSD)     |

安装核心组件：

```
bash

sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv python3.12-dev \
                    nginx git certbot python3-certbot-nginx \
                    postgresql libpq-dev
```

## 2. 部署流程

### 2.1 创建运行用户与目录

```
bash

sudo useradd -m -s /bin/bash assetadmin
sudo usermod -aG www-data assetadmin
sudo mkdir -p /var/www/asset-management
sudo chown -R assetadmin:assetadmin /var/www/asset-management
```

### 2.2 拉取代码与虚拟环境

```
bash

sudo su - assetadmin
cd /var/www/asset-management
git clone <your-repo-url> .
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements/prod.txt   # 生产依赖
deactivate
exit
```

### 2.3 环境变量

```
bash

cp .env.example .env
sudo nano .env
```

| 变量                                    | 说明                        |
| ------------------------------------- | ------------------------- |
| `DJANGO_SECRET_KEY`                   | `openssl rand -hex 32` 生成 |
| `DJANGO_DEBUG`                        | `False`                   |
| `ALLOWED_HOSTS`                       | 域名，逗号分隔                   |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` | PostgreSQL 数据库凭据            |
| `DB_HOST`                             | 通常为 `localhost`           |
| `DB_PORT`                             | 默认 `5432`                 |
| `REDIS_URL`                           | Redis 连接地址,Docker 环境使用 `redis://redis:6379/0` |

> **启动校验**：生产环境（`DJANGO_SETTINGS_MODULE=config.settings.production`）会在启动时校验以下变量,缺失时直接报错退出：
> - `SECRET_KEY`、`ALLOWED_HOSTS`、`DB_PASSWORD`、`REDIS_URL`
> - CI/CD 中的 `collectstatic`、`migrate` 等管理命令也需设置这些变量
>
> **⚠️ init-once 语义**：以下变量**仅在数据卷首次创建时生效**,后续修改 `.env` 不会自动更新：
> - `DB_PASSWORD` / `DB_USER` / `DB_NAME`（PostgreSQL 初始化脚本仅执行一次）
> - `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`（Grafana 首次启动创建管理员,后续不变）
>
> **存量环境凭据轮换路径**：
> - PostgreSQL：`ALTER USER <user> PASSWORD '<new_password>';`（需数据库连接权限）
> - Grafana：`grafana-cli admin reset-admin-password <new_password>`（容器内执行）或通过 Web UI → Configuration → Users

---

## 3. 数据库（PostgreSQL 16）

### 3.1 创建库与用户

```
bash

sudo -u postgres psql
CREATE DATABASE asset_db ENCODING 'UTF8';
CREATE USER asset_user WITH PASSWORD 'strong-password';
GRANT ALL PRIVILEGES ON DATABASE asset_db TO asset_user;
\q
```

### 3.2 迁移与静态文件

```
bash

sudo su - assetadmin
cd /var/www/asset-management
source venv/bin/activate
python manage.py migrate
python manage.py collectstatic --noinput

# 可选：创建超级管理员

python manage.py createsuperuser
deactivate
```

---

## 4. Gunicorn (WSGI)

创建服务文件 `/etc/systemd/system/asset-management.service`：

```
ini

[Unit]
Description=Gunicorn for asset management
After=network.target postgresql.service
[Service]
User=assetadmin
Group=www-data
WorkingDirectory=/var/www/asset-management
Environment="PATH=/var/www/asset-management/venv/bin"
ExecStart=/var/www/asset-management/venv/bin/gunicorn \
    --workers 3 --threads 2 --timeout 120 \
    --bind 127.0.0.1:8000 \
    --access-logfile /var/log/asset-management/gunicorn-access.log \
    --error-logfile /var/log/asset-management/gunicorn-error.log \
    config.wsgi:application
Restart=always
[Install]
WantedBy=multi-user.target
```

启动服务：

```
bash

sudo mkdir -p /var/log/asset-management
sudo chown -R assetadmin:www-data /var/log/asset-management
sudo systemctl daemon-reload
sudo systemctl enable --now asset-management
```

---

## 5. Nginx (反向代理)

### 5.1 配置站点

创建 `/etc/nginx/sites-available/asset-management`：

```
nginx

upstream asset_backend { server 127.0.0.1:8000; }
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    access_log /var/log/nginx/asset-management-access.log;
    error_log /var/log/nginx/asset-management-error.log;
    location /static/ {
        alias /var/www/asset-management/static/;
        expires 30d;
    }
    location /media/ {
        alias /var/www/asset-management/media/;
        expires 30d;
    }
    location / {
        proxy_pass http://asset_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    # 安全头
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";
    add_header Referrer-Policy strict-origin-when-cross-origin;
}
```

启用配置：

```
bash

sudo ln -s /etc/nginx/sites-available/asset-management /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

---

## 6. HTTPS (Let’s Encrypt)

```
bash

sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# 测试自动续期
sudo certbot renew --dry-run
```

---

## 7. 防火墙 (UFW)

```
bash

sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## 8. 日志与监控

- **日志轮转**（创建 `/etc/logrotate.d/asset-management`）：

```text
  /var/log/asset-management/*.log {

      daily
      rotate 14
      compress
      delaycompress
      notifempty
      create 0640 assetadmin www-data
      sharedscripts
      postrotate
          systemctl reload asset-management > /dev/null 2>&1 || true
      endscript

  }
```

- 实时日志：`sudo journalctl -u asset-management -f`

---

## 9. 备份策略

### 数据库备份脚本

`/var/www/asset-management/scripts/backup-db.sh`：

```
bash

#!/bin/bash
BACKUP_DIR="/var/backups/asset-management/db"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# 使用 pg_dump 备份 PostgreSQL 数据库（需提前配置 ~/.pgpass 认证）
pg_dump asset_db | gzip > $BACKUP_DIR/db_$DATE.sql.gz
find $BACKUP_DIR -name "db_*.sql.gz" -mtime +30 -delete
```

> 为避免密码明文泄露，建议创建 `~/.pgpass` 文件：

> `text`
> 
> `localhost:5432:asset_db:asset_user:strong-password`

添加定时任务：

```
bash

chmod +x /var/www/asset-management/scripts/backup-db.sh
sudo crontab -e

# 每天凌晨2点
0 2 * * * /var/www/asset-management/scripts/backup-db.sh
```

> 🔴 **上线前必做**：确保数据库迁移可逆 (`python manage.py migrate assetmanagement <上一版本号>` 能成功回滚)。

---

## 10. 部署自检清单

| 类别      | 检查项                                        |
| ------- | ------------------------------------------ |
| **系统**  | ✅ Python 3.12、PostgreSQL、Nginx 安装正确        |
| **项目**  | ✅ 虚拟环境已创建，生产依赖安装完整                         |
| **配置**  | ✅ `DEBUG=False`，`ALLOWED_HOSTS` 已设置，密钥强度足够 |
| **数据库** | ✅ 迁移已执行，静态文件已收集，超级管理员已创建（如需要）              |
| **服务**  | ✅ `asset-management.service` 正常运行，开机自启     |
|         | ✅ Nginx 配置通过测试，反向代理正常工作                    |
| **安全**  | ✅ HTTPS 证书已配置，防火墙仅开放 22/80/443             |
|         | ✅ 数据库密码强度足够，`.env` 未入库                     |
| **备份**  | ✅ 数据库备份脚本可执行，定时任务已配置                       |
| **验证**  | ✅ 核心 API 接口返回正常（用 curl 测试）                 |

---

## 11. 常见问题

**Gunicorn 启动失败**

```
bash

sudo journalctl -u asset-management -n 50
# 常见原因：虚拟环境路径错误、数据库连接失败、端口占用
```

**Nginx 502 Bad Gateway**  
检查 Gunicorn 是否运行：`sudo systemctl status asset-management`  
查看 Nginx 错误日志：`tail -n 50 /var/log/nginx/asset-management-error.log`

**静态文件 404**  
确认已执行 `collectstatic`，且 Nginx `alias` 路径正确。

**PostgreSQL 连接问题**  
检查 `.env` 中数据库配置、PostgreSQL 用户权限，以及 `listen_addresses`（通常设为 `127.0.0.1`）。
