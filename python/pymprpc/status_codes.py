"""定义mprpc的响应状态码和对应的默认状态信息.

+ File: status_codes.py
+ Version: 0.5
+ Author: hsz
+ Email: hsz1273327@gmail.com
+ Copyright: 2018-02-08 hsz
+ License: MIT
+ History

    + 2018-01-23 created by hsz
    + 2018-01-23 version-0.5 by hsz
"""

STATUS_CODES = {
    50: 'Broker Login Succeed',
    51: 'Broker Login Error',
    100: 'Continue',
    200: 'OK',
    201: 'Response is Stream',
    202: 'Stream Content',
    203: 'Response is Heartbeat',
    206: 'Stream End',
    300: 'ExpireWarning',
    301: 'ExpireStreamWarning',
    400: 'Bad Request',
    401: 'Not Find Method',
    402: 'Param Error',
    403: 'Restrict Access',
    404: 'RPC RuntimeError',
    405: 'Result Limited',
    406: 'Unsupport SysMethod',
    500: 'Server Error',
    501: 'Login Error',
    502: 'Server Requirement Error',
    503: 'Service Unavailable',
    504: 'Connection Timeout',
    505: 'Wrong Protocol',
    506: 'Protocol Syntax Error'
}
