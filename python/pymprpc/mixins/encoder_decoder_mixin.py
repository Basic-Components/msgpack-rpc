"""定义mprpc客户端和服务器中通用的编码解码混入类.

+ File: encoder_decoder_mixin.py
+ Version: 0.5
+ Author: hsz
+ Email: hsz1273327@gmail.com
+ Copyright: 2018-02-08 hsz
+ License: MIT
+ History

    + 2018-01-23 created by hsz
    + 2018-01-23 version-0.5 by hsz
"""
try:
    import ujson as json
except ModuleNotFoundError:
    import json
from typing import (
    Dict,
    Any
)
import msgpack
from pymprpc.errors import (
    ProtocolException
)


class EncoderDecoderMixin:
    """编码解码混入类,用于从读入的字节串中解码出数据,或者将数据编码为字节串.

    需要被混入的类中有:

    Attributes:

        SEPARATOR (bytes): - 用于标明读取字节终止符
        VERSION (str): - 标识协议版本

    """

    def encoder(self, query: Dict[str, Any]):
        """编码请求为bytes.

        检查是否使用debug模式和是否对数据进行压缩.之后根据状态将python字典形式的请求编码为字节串.

        Parameters:

            query (Dict[str, Any]): - python字典形式的请求数据

        Return:

            (bytes): - 请求的字节串

        """
        if self.debug is True:
            queryb = json.dumps(
                query,
                ensure_ascii=False).encode("utf-8")
        else:
            queryb = msgpack.packb(query)

        if self.compreser:
            queryb = self.compreser.compress(queryb)

        return queryb + self.SEPARATOR

    def decoder(self, response: bytes):
        """编码请求为bytes.

        检查是否使用debug模式和是否对数据进行压缩.之后根据状态将python字典形式的请求编码为字节串.

        Parameters:

            response (bytes): - 响应的字节串编码

        Return:

            (Dict[str, Any]): - python字典形式的响应

        """
        response = response[:-(len(self.SEPARATOR))]
        if self.compreser is not None:
            response = self.compreser.decompress(response)
        if self.debug is True:
            response = json.loads(response.decode('utf-8'))
        else:
            response = msgpack.unpackb(response, encoding='utf-8')
        version = response.get("MPRPC")
        if version and version == self.VERSION:
            return response
        else:
            raise ProtocolException("Wrong Protocol")
