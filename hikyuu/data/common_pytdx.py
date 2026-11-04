# coding:utf-8
#
# The MIT License (MIT)
#
# Copyright (c) 2010-2019 fasiondog/hikyuu
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
import time
import importlib.util
from concurrent import futures
from pytdx.hq import TdxHq_API
from pytdx.config.hosts import hq_hosts


def _to_host_tuple(host):
    """将 (名称, ip, port) 或 (ip, port) 归一化为 (ip, port)"""
    if len(host) >= 3:
        return (host[1], host[2])
    return (host[0], host[1])


def _resolve_hosts_file():
    """按优先级查找通达信行情服务器配置文件 (hosts.py)，未找到时返回 None

    1. 环境变量 HKU_TDX_HOSTS 指定的文件；
    2. 项目根目录下的 hosts.py（源码运行时为 hikyuu 包的上级目录，pip 安装时该路径通常不存在）；
    3. 用户目录下的 ~/.hikyuu/hosts.py。
    """
    candidates = [os.environ.get('HKU_TDX_HOSTS')]
    module_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(os.path.dirname(module_dir))
    candidates.append(os.path.join(project_dir, 'hosts.py'))
    candidates.append(os.path.expanduser('~/.hikyuu/hosts.py'))
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def _load_hosts_file(path):
    """从指定的 hosts.py 中读取 hq_hosts，读取失败时返回 None（不影响主流程）"""
    try:
        spec = importlib.util.spec_from_file_location('hikyuu_tdx_hosts', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        hosts = getattr(module, 'hq_hosts', None)
        return list(hosts) if hosts else None
    except Exception:
        return None


# 自定义地址为空时回落到 pytdx 内置的地址列表
_hosts_file = _resolve_hosts_file()
_user_hosts = _load_hosts_file(_hosts_file) if _hosts_file else None
if _user_hosts:
    hq_hosts = _user_hosts


def to_pytdx_market(market):
    """转换为pytdx的market"""
    pytdx_market = {'SZ': 0, 'SH': 1, 'BJ': 2}
    return pytdx_market[market.upper()]


def ping(ip, port=7709, multithread=False, timeout=1):
    api = TdxHq_API(multithread=multithread)
    success = False
    starttime = time.time()
    success = False
    try:
        if api.connect(ip, port, time_out=timeout):
            # x = api.get_security_count(0)
            # x = api.get_index_bars(7, 1, '000001', 800, 100)
            x = api.get_security_bars(7, 0, '000001', 800, 100)
            if x:
                success = True
            api.close()
    except Exception as e:
        print(e)
        pass
    endtime = time.time()
    return (success, endtime - starttime, ip, port)


def search_best_tdx():
    """搜索可用的通达信行情服务器，返回 (成功, 耗时, ip, port) 列表，按耗时排序

    服务器地址来自 pytdx 内置的 hq_hosts，可用 ~/.hikyuu/hosts.py 中的同名列表覆盖；
    用户自定义的地址视为可信，直接按配置顺序返回（不做K线探测，兼容只提供
    股票列表/财务等元数据的服务器）。
    """
    def ping2(host):
        return ping(host[0], host[1], host[2])

    if _user_hosts:
        return [(True, 0.0) + _to_host_tuple(host) for host in _user_hosts]

    hosts = [_to_host_tuple(host) + (True,) for host in hq_hosts]
    pinged = []
    with futures.ThreadPoolExecutor() as executor:
        # 不使用 executor.map(timeout=...)：整体的 map 超时会让整个搜索直接抛出 TimeoutError
        tasks = [executor.submit(ping2, host) for host in hosts]
        for task in futures.as_completed(tasks):
            try:
                res = task.result()
            except Exception:
                continue
            if res[0]:
                pinged.append(res)
    pinged.sort(key=lambda item: item[1])

    # 校验 host 是否存在错误，取同样数据，相同结果最多的集合
    values = {}
    for host in pinged:
        api = TdxHq_API(multithread=False)
        if api.connect(host[2], host[3]):
            bars = api.get_security_bars(9, 0, '159915', 0, 1)
            if bars and len(bars) > 0:
                if bars[0]['close'] not in values:
                    values[bars[0]['close']] = [host]
                else:
                    values[bars[0]['close']].append(host)
            api.close()
    ret = []
    for _, host in values.items():
        if len(host) > len(ret):
            ret = host

    # 数据一致性校验全部失败时，退化为可ping通的服务器，避免误判为无可用服务器
    return ret if ret else pinged


def pytdx_get_day_trans(api, pymarket, code, date):
    buf = []
    for i in range(21):
        x = api.get_history_transaction_data(pymarket, code, i * 2000, 2000,
                                             date)
        # x = api.get_transaction_data(TDXParams.MARKET_SZ, '000001', (9-i)*800, 800)
        if not x:
            break
        buf = x + buf
    return buf


if __name__ == '__main__':
    import time
    starttime = time.time()

    x = search_best_tdx()
    for i in x:
        print(i)
    print(len(x))
    print(len(hq_hosts))

    endtime = time.time()
    print("\nTotal time:")
    print("%.2fs" % (endtime - starttime))
    print("%.2fm" % ((endtime - starttime) / 60))
