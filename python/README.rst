
pymprpc
===============================

* version: 0.0.3

* status: dev

* author: hsz

* email: hsz1273327@gmail.com

Desc
--------------------------------

 a rpc framework for message-pack rpc.


keywords:rpc,server,tcp


Feature
----------------------
* api seems to stdlib xmlrpc
* easy to use, easy to debug
* support stream response

Example
-------------------------------

server

.. code:: python

    import platform
    from pymprpc.server import SimpleMprpcServer
    if platform.system() == "Windows":
        try:
            import aio_windows_patch as asyncio
        except:
            import warnings
            warnings.warn(
                "you should install aio_windows_patch to support windows",
                RuntimeWarning,
                stacklevel=3)
            import asyncio

    else:
        import asyncio
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass


    class MyMPRPCServer(SimpleMprpcServer):
        pass


    with MyMPRPCServer(("127.0.0.1", 5000), debug=True) as server:
        server.register_introspection_functions()

        @server.register_function()
        def testfunc(a, b):
            '''有help'''
            return a + b

        @server.register_function()
        async def testcoro(a, b):
            await asyncio.sleep(0.1)
            return a + b

        @server.register_function()
        async def testcorogen(a, b):
            for i in range(10):
                await asyncio.sleep(0.1)
                yield i + a + b

        class TestClass:

            def testclassmethod(self, a, b):
                return a + b

            async def testclasscoro(self, a, b):
                await asyncio.sleep(0.1)
                return a + b

            async def testclasscorogen(self, a, b):
                for i in range(10):
                    await asyncio.sleep(0.1)
                    yield i + a + b
        t = TestClass()
        server.register_instance(t)
        server.run_forever()


sync client

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



async client

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


Install
--------------------------------

- ``python -m pip install pymprpc``


Documentation
--------------------------------

`Documentation on Readthedocs <https://github.com/Basic-Components/msgpack-rpc-protocol>`_.



TODO
-----------------------------------

* Load balancing broker

Limitations
-----------

* sync client do not support heartbeat and timeout

