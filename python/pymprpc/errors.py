"""定义mprpc的标准错误和一些方法.

+ File: errors.py
+ Version: 0.5
+ Author: hsz
+ Email: hsz1273327@gmail.com
+ Copyright: 2018-02-08 hsz
+ License: MIT
+ History

    + 2018-01-23 created by hsz
    + 2018-01-23 version-0.5 by hsz
"""
from pymprpc.status_codes import STATUS_CODES

_mprpc_exceptions = {}  # 注册的异常保存在其中用于查找


def add_status_code(code):
    """用于将mprpc的标准异常注册到`_mprpc_exceptions`的装饰器.

    Parameters:
        code (int): - 标准状态码
    Return:
        (Callable): - 装饰函数

    """
    def class_decorator(cls):
        """内部装饰函数,用于将异常类注册到对应的状态码.

        Parameters:
            cls (Callable): - 要注册的异常类
        Return:
            (Callable): - 注册的异常类

        """
        cls.status_code = code
        _mprpc_exceptions[code] = cls
        return cls

    return class_decorator


class MprpcException(Exception):
    """mprpc标准异常类.

    Attributes:
        status_code (int): - 状态码

    """

    def __init__(self,
                 message: str,
                 status_code: int=None):
        """初始化异常.

        Parameters:

            message (str): - 异常信息
            status_code (int): - 状态码

        """
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


class MethodError(MprpcException):
    """mprpc的远程函数执行异常类.

    Attributes:

        status_code (int): - 状态码
        ID (str): - 执行任务的ID
        EXCEPTION (str): - 错误的异常栈信息

    """

    def __init__(self, message, ID, exception=None, status_code=None):
        """初始化异常.

        Parameters:

            message (str): - 异常信息
            ID (str): - 任务ID
            exception (str): - 异常栈信息
            status_code (int): - 状态码

        """
        super().__init__(message, status_code)
        self.ID = ID
        self.EXCEPTION = exception


class ServerException(MprpcException):
    """mprpc的服务异常类.

    Attributes:
        status_code (int): - 状态码

    """

    pass


class BrokerException(MprpcException):
    """mprpc的中介异常类.

    Attributes:
        status_code (int): - 状态码

    """

    pass


@add_status_code(51)
class BrokerLoginError(BrokerException):
    """登录中介错误."""

    pass


@add_status_code(400)
class RequestError(MethodError):
    """请求错误."""

    pass


@add_status_code(401)
class NotFindError(MethodError):
    """未找到对应的函数错误."""

    pass


@add_status_code(402)
class ParamError(MethodError):
    """请求的参数与签名不符错误."""

    pass


@add_status_code(403)
class RestrictAccessError(MethodError):
    """限制访问对应函数错误."""

    pass


@add_status_code(404)
class RPCRuntimeError(MethodError):
    """函数执行错误."""

    pass


@add_status_code(405)
class ResultLimitError(MethodError):
    """返回的结果超过限制的字节限制错误."""

    pass


@add_status_code(406)
class UnsupportSysMethodError(MethodError):
    """不支持的服务器固有方法错误."""

    pass


@add_status_code(500)
class RpcException(ServerException):
    """服务器异常."""

    pass


@add_status_code(501)
class LoginError(ServerException):
    """登录失败异常."""

    pass


@add_status_code(502)
class RequirementException(ServerException):
    """服务器的依赖服务异常."""

    pass


@add_status_code(503)
class RpcUnavailableException(ServerException):
    """服务器不可用异常."""

    pass


@add_status_code(504)
class TimeoutException(ServerException):
    """服务器连接超时异常."""

    pass


@add_status_code(505)
class ProtocolException(ServerException):
    """协议错误."""

    pass


@add_status_code(506)
class ProtocolSyntaxException(ServerException):
    """协议语法错误."""

    pass


def abort(status_code: int,
          ID: str=None,
          exception: str="",
          message: str=None):
    """根据状态码创建一个异常.

    Parameters:
        status_code (int): - 错误的状态码
        ID (str): - 任务的ID号,通常是一个uuid,默认为None,服务错误不需要ID,方法调用错误需要ID
        exception (): - 错误的异常栈信息,默认为None,服务错误不需要,方法调用错误可以需要
        message (str): - 错误信息

    Return:
        (MprpcException): - 指定错误码对应的mprpc标准异常

    """
    if message is None:
        message = STATUS_CODES.get(status_code)
        # These are stored as bytes in the STATUS_CODES dict
    mprpc_exception = _mprpc_exceptions.get(status_code, MprpcException)
    if issubclass(mprpc_exception, MethodError) or (
            mprpc_exception is MethodError):
        return mprpc_exception(
            message=message,
            ID=ID,
            exception=exception,
            status_code=status_code)

    return mprpc_exception(
        message=message,
        status_code=status_code)
