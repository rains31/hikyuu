# -*- coding: utf-8 -*-
"""
通达信(pytdx)行情服务器探测工具

用途：在 pytdx 内置地址（+ 自定义候选地址）中筛出本机真正可达、且能返回数据的服务器，
并按可直接粘贴的格式输出 hq_hosts 配置，供 hosts.py 使用。

用法：
    python docs/tools/probe_tdx_hosts.py                # 探测内置 + 内置常见新地址
    python docs/tools/probe_tdx_hosts.py 1.2.3.4:7709   # 追加探测指定地址
    python docs/tools/probe_tdx_hosts.py --bars         # 只看能返回K线的服务器

结果写入位置（hikyuu 按此优先级自动加载）：
    1. 环境变量 HKU_TDX_HOSTS 指定的文件
    2. 项目根目录 hosts.py
    3. ~/.hikyuu/hosts.py
"""
import sys
import socket
from concurrent import futures

from pytdx.hq import TdxHq_API
from pytdx.config.hosts import hq_hosts

# pytdx 内置列表之外的常见地址
EXTRA = [
    ('119.147.212.81', 7709), ('124.71.187.11', 7709), ('122.51.120.210', 7709),
    ('110.41.147.114', 7709), ('110.41.4.4', 7709), ('124.70.176.52', 7709),
    ('111.230.186.65', 7709), ('110.41.2.72', 7709), ('124.71.168.113', 7709),
    ('175.178.112.113', 7709), ('183.236.98.40', 7709), ('120.79.101.249', 7709),
    ('123.56.92.224', 7709), ('58.254.39.146', 7709), ('116.205.183.151', 7709),
    ('124.70.199.66', 7709), ('47.107.63.89', 7709), ('218.108.98.230', 7709),
]


def parse_args(argv):
    """解析命令行参数，返回 (是否只保留K线可用, 额外地址列表)"""
    bars_only = '--bars' in argv
    extra = []
    for arg in argv:
        if arg.startswith('--'):
            continue
        ip, _, port = arg.partition(':')
        extra.append((ip, int(port) if port else 7709))
    return bars_only, extra


def tcp_ok(ip, port, timeout=2):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def probe(item):
    """探测单个地址：先TCP连通性，再依次检查K线 / 股票列表 / 实时行情"""
    ip, port = item
    if not tcp_ok(ip, port):
        return None
    api = TdxHq_API(heartbeat=False)
    try:
        if not api.connect(ip, port, time_out=4):
            return None
    except Exception:
        return None

    result = {}
    for name, fn in (('bars', lambda: api.get_security_bars(9, 0, '159915', 0, 5)),
                     ('index_bars', lambda: api.get_index_bars(9, 1, '000001', 0, 5)),
                     ('stock_count', lambda: api.get_security_count(0)),
                     ('stock_list', lambda: api.get_security_list(0, 0)),
                     ('quotes', lambda: api.get_security_quotes([(1, '600000')]))):
        try:
            r = fn()
            result[name] = len(r) if isinstance(r, (list, dict)) else (r if isinstance(r, int) else 0)
        except Exception:
            result[name] = 0
    try:
        api.close()
    except Exception:
        pass

    has_bars = result['bars'] > 0 or result['index_bars'] > 0
    has_meta = result['stock_count'] > 0 or result['stock_list'] > 0
    return (ip, port, has_bars, has_meta, result)


def main():
    bars_only, extra = parse_args(sys.argv[1:])
    targets = [(h[1], h[2]) for h in hq_hosts] + EXTRA + extra

    with futures.ThreadPoolExecutor(max_workers=32) as ex:
        results = [r for r in ex.map(probe, targets) if r]

    bar_hosts = [r for r in results if r[2]]
    meta_hosts = [r for r in results if r[3] and not r[2]]
    print('探测总数: {} | 可连通: {} | 能返回K线: {} | 仅元数据(股票列表): {}'.format(
        len(targets), len(results), len(bar_hosts), len(meta_hosts)))

    def dump(title, hosts):
        print('\n# {}（可直接粘贴到 hosts.py）'.format(title))
        print('hq_hosts = [')
        for ip, port, _, _, _ in hosts:
            print('    ("{}", "{}", {}),'.format(ip, ip, port))
        print(']')

    if bar_hosts:
        dump('能返回K线的服务器（优先使用，在线导入K线可用）', bar_hosts)
    if not bars_only and meta_hosts:
        dump('仅能返回股票列表的服务器（可在线导入代码表，K线请用 vipdoc 离线导入）', meta_hosts)
    if not bar_hosts and not meta_hosts:
        print('\n没有可用服务器：请检查网络/代理，或用 python docs/tools/probe_tdx_hosts.py ip:port 追加候选地址')
    return 0


if __name__ == '__main__':
    sys.exit(main())
