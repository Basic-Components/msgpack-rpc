"""mprpc的python客户端.
>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

Python客户端只支持python3.6+,并提供同步接口SyncRPC和异步接口AsyncRPC

+ File: client.__init__.py
+ Version: 0.5
+ Author: hsz
+ Email: hsz1273327@gmail.com
+ Copyright: 2018-02-08 hsz
+ License: MIT
+ History

    + 2018-01-23 created by hsz
    + 2018-02-08 version-0.5 by hsz


异步接口使用方法
::::::::::::::::::::

.. code:: python

    import asyncio
    from pymprpc.client import AsyncRPC


    async def main(loop):
        async with AsyncRPC(
                addr="tcp://admin:admin@127.0.0.1:5000",
                loop=loop,
                debug=True) as rpc:
            print(await rpc.system.listMethods())
            print(await rpc.system.methodSignature("testclassmethod"))
            print(await rpc.system.methodHelp("testfunc"))
            print(await rpc.system.lenConnections())
            print(await rpc.system.lenUndoneTasks())
            print(await rpc.testclassmethod(1, 2))
            print(await rpc.testclasscoro(2, 3))
            print(await rpc.testcoro(5, 6))
            print(await rpc.testfunc(5, 4))
            # await asyncio.sleep(200)
            print("wait done")
            print(await rpc.testfunc())
        print("end")
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main(loop))
    except Exception as e:
        raise e


同步接口使用方法
::::::::::::::::::::

.. code:: python

    import time
    from pymprpc.client import RPC

    with RPC(addr="tcp://admin:admin@127.0.0.1:5000",
             debug=True) as rpc:
        print(rpc.system.listMethods())
        print(rpc.system.methodSignature("testclassmethod"))
        print(rpc.system.methodHelp("testfunc"))
        print(rpc.system.lenConnections())
        print(rpc.system.lenUndoneTasks())
        print(rpc.testclassmethod(1, 2))
        print(rpc.testclasscoro(2, 3))
        print(rpc.testcoro(5, 6))
        print(rpc.testfunc(5, 4))
        agen = rpc.testcorogen(1, 2)
        for i in agen:
            print(i)
        time.sleep(200)
        print("wait done")
        # rpc.close()
        print(rpc.testfunc())

"""
from .aio import AsyncRPC
from .sync import RPC


__all__ = ["AsyncRPC", "RPC"]
