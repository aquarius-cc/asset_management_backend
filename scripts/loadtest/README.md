# M-4 压测基线方案（预发独立 + token 池，非 CI）

依据: M-4 方案 §方案（预发环境独立、token 池、不进 CI 流程）
状态: A 阶段已完成（本文档 = 基线报告模板）；压测执行 = 发布前手动执行（依赖 M-1 限流修复 + token 生成脚本已存在）

## 环境条件
- 预发环境（.env.production.test 域名独立，DB 独立）
- M-1 限流修复已落地（独立 login_brute zone）
- token 生成：python scripts/loadtest/gen_tokens.py 50

## 压测脚本
- scripts/loadtest/gen_tokens.py
- scripts/loadtest/locustfile_asset_list.py（列表）
- scripts/loadtest/locustfile_dashboard.py（聚合）
- scripts/loadtest/locustfile_asset_create.py（写入）
- scripts/loadtest/README.md（本文件）

## 执行档位
并发: 10 / 50 / 100 vuser  × 10min
命令: locust -f scripts/loadtest/locustfile_asset_list.py --host=https://<PRE_DOMAIN> --users 50 --spawn-rate 10 --run-time 10m --html=docs/loadtest/report_list.html

## 目标基线（对齐告警阈值）
- P95 < 1.0s（告警线 > 2.0s 需 2 倍余量）
- 错误率 < 1%（告警线 > 5%）
- RPS 稳定（无 429 激增，证明限流与压测无干扰）

## 数据清理
python -c "
import django, os
os.environ['DJANGO_SETTINGS_MODULE']='config.settings.test'
django.setup()
from apps.authusermanagement.models import AuthUser
AuthUser.objects.filter(username__startswith='loadtest_user_').delete()
"

## 报告格式
报告写入 docs/性能压测基线_YYYY-MM-DD.md，含 P50/P95/P99、错误率、DB 连接数峰值、CPU/内存水位、RPS 基线、与告警阈值的对比关系。
