# -*- coding: utf-8 -*-
"""
datasources/adapters.py —— 数据源适配器层

把各数据源的「反爬 header / 分页 / 编码 / WAF」坑封装成统一接口，
接口一变只改这里；返回统一 DataFrame + 落 CSV。

设计约定：
  - 每个 fetch_* 返回 pandas.DataFrame，并写入 下载资料/<章节+来源>.csv；
  - 每个源标注 `最后验证日期`（接口变了先看这里）；
  - fetch 失败抛出带「降级建议」的异常，由调用方沿降级链切换（见权威源映射.yaml 降级链）。

已知边界（本次实测）：
  - 上交所：需 Referer=https://www.sse.com.cn/，返回老式 .xls（OLE2），用 xlrd 解析；
  - 深交所：projectrends 的 page/start/count 均失效，只有 pageSize 生效且 offset 无效，
    只能拿前 pageSize 条（pageSize 上限约 100）——「全量」拿不到，需降级 iFinD；
  - 证监会：必须 http 非 https（https SSL 握手失败），翻页 csrcfd/index_N.html；
  - 北交所：bse.cn 连接被 WAF 重置（ConnectionResetError 10054），暂无 MCP 直连方案。
"""
import os
import sys
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# pandas / requests 均为重/可选依赖，延迟导入（避免 import adapters 即崩，也避免导入副作用）
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '下载资料')


def _ensure_out():
    os.makedirs(DEFAULT_OUT, exist_ok=True)


def _pd():
    import pandas as pd
    return pd


def _requests():
    import requests
    return requests

SSE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Referer': 'https://www.sse.com.cn/',
    'Accept': '*/*',
}
SZSE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36',
    'Referer': 'https://listing.szse.cn/projectdynamic/ipo/index.html',
    'Accept': 'application/json, text/plain, */*',
    'X-Request-Type': 'ajax',
}

# 各源最后验证日期（接口变了先更新这里再修代码）
LAST_VERIFIED = {
    'sse': '2026-08-27',
    'szse': '2026-08-27',
    'csrc': '2026-08-27',
    'bse': '2026-08-27（WAF 拦截，不可用）',
}


class SourceError(Exception):
    def __init__(self, source, msg, fallback):
        super().__init__(msg)
        self.source = source
        self.fallback = fallback


def _save(df, name):
    _ensure_out()
    out = os.path.join(DEFAULT_OUT, name)
    df.to_csv(out, index=False, encoding='utf-8-sig')
    return out


def fetch_sse(sql_id, out_name):
    """上交所科创板 IPO/再融资/并购。sql_id: SH_XM_LB / GP_ZRZ_XMLB / GP_BGCZ_XMLB"""
    url = 'https://query.sse.com.cn/commonExcelKcb.do?sqlId=%s' % sql_id
    try:
        r = _requests().get(url, headers=SSE_HEADERS, timeout=30)
        r.raise_for_status()
    except Exception as e:
        raise SourceError('sse', '上交所请求失败: %s' % e,
                          '降级：mx-ds-mcp / iFinD(hexin-ifind-ds) 兜底')
    try:
        from io import BytesIO
        data = BytesIO(r.content)
        df = _pd().read_excel(data, engine='xlrd', header=0)
    except Exception as e:
        raise SourceError('sse', '上交所 xls 解析失败: %s' % e, '降级：iFinD')
    out = _save(df, out_name)
    return df, out


def fetch_szse(biz_type, out_name, page_size=100):
    """深交所 IPO(1)/再融资(2)/并购(3)。注意：只能拿前 page_size 条，全量需降级 iFinD。"""
    rows = []
    u = ('https://www.szse.cn/api/ras/projectrends/query?bizType=%d'
         '&random=0.%06d&start=0&pageSize=%d' % (biz_type, int(time.time() * 1000) % 1000000, page_size))
    try:
        j = _requests().get(u, headers=SZSE_HEADERS, timeout=30).json()
        if not isinstance(j, dict):
            raise ValueError('深交所返回非 JSON 对象（分页/接口可能失效）')
        data = j.get('data', [])
        total = j.get('totalSize', 0)
    except SourceError:
        raise
    except Exception as e:
        raise SourceError('szse', '深交所请求失败: %s' % e, '降级：iFinD / mx-ds-mcp')
    df = _pd().DataFrame(data)
    out = _save(df, out_name)
    if total > len(data):
        print('[警告] 深交所 %s 仅取到 %d/%d 条（分页失效），全量请用 iFinD 兜底'
              % (out_name, len(data), total))
    return df, out


def fetch_csrc_tutoring(out_name='证监会官网-A股辅导备案_全量.csv', max_pages=60):
    """证监会辅导备案（http 非 https，翻页 csrcfd/index_N.html）。"""
    H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    import re
    rows = []
    for page in range(1, max_pages + 1):
        url = 'http://eid.csrc.gov.cn/fd.html' if page == 1 \
            else 'http://eid.csrc.gov.cn/csrcfd/index_%d.html' % page
        try:
            r = _requests().get(url, headers=H, timeout=20)
            raw = r.content
            # csrc 官网常用 GBK/GB2312；按内容做 gbk / utf-8 回退
            try:
                html = raw.decode('gbk')
            except UnicodeDecodeError:
                html = raw.decode('utf-8', errors='ignore')
        except Exception as e:
            raise SourceError('csrc', '证监会辅导备案请求失败: %s' % e, '降级：iFinD辅导备案')
        trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S)
        got = 0
        for tr in trs:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)
            clean = [re.sub(r'<[^>]+>', '', t).strip() for t in tds]
            if len(clean) >= 5 and clean[1]:
                rows.append(clean)
                got += 1
        if got == 0:
            break
        time.sleep(0.3)
    df = _pd().DataFrame(rows, columns=['序号', '公司名称', '辅导机构', '日期', '状态', '证监局', '文件类型', '标题'])
    out = _save(df, out_name)
    return df, out


def fetch_bse(*args, **kwargs):
    """北交所：WAF 拦截，直连不可用。"""
    raise SourceError('bse',
                      'bse.cn 连接被 WAF 重置（ConnectionResetError 10054），直连不可用',
                      '降级：iFinD 北交所审核项目；拿不到则标注「本期无法获取」')


def health_check():
    """一键自检：哪些源当前可用。"""
    result = {}
    for name, fn, args in [
        ('sse', fetch_sse, ('SH_XM_LB', '上交所官网-A股IPO审核-科创板项目列表.csv')),
        ('szse', fetch_szse, (1, '深交所官网-A股IPO审核.csv')),
        ('csrc', fetch_csrc_tutoring, ('证监会官网-A股辅导备案_全量.csv',)),
    ]:
        try:
            df, _ = fn(*args)
            result[name] = '✅ 可用（%d 行）' % len(df)
        except SourceError as e:
            result[name] = '❌ 不可用：%s' % e
    result['bse'] = '❌ 不可用（WAF 拦截）'
    return result


if __name__ == '__main__':
    print('=== 数据源自检 ===')
    for k, v in health_check().items():
        print('%s: %s' % (k, v))
    print('最后验证日期：', LAST_VERIFIED)
