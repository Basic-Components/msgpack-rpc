# MESSAGE-PACK-RPC

+ 起始时间:2018-1-22
+ 版本:0.1
+ 作者:hsz

## 概述

MESSAGE-PACK-RPC是一个轻量级的无状态远程过程调用(RPC)应用层协议.它参考自JSON-RPC 2.0协议,
但它是独立的也不向JSON-RPC协议兼容.

本规范主要定义了一些数据结构及其相关的处理规则.它允许运行在基于tcp协议的消息传输环境中,
使用messagepack作为序列化和反序列化数据格式进行通信.

与json-rpc不同,message-pack-rpc的个请求形式可以有

+ 应答模式,一问一答. 类似函数调用
+ 服务端在获取请求后向客户端进行推送. 类似于调用一个生成器

注意流操作依然是使用的一般的应答,而非流式服务器.

其他的特性包括:

+ 服务器端对连接建立的客户端可以有权限检验,也就是说可以设定口令

+ 客户端主动关闭连接,服务端可以设置过期时间主动断开连接,默认为180秒.

+ 允许设置客户端类型检查默认为True

+ 允许客户端设定心跳以维持连接不会过期断开.默认为False

+ 支持使用json替代message-pack,该模式为DEBUG模式,默认不使用DEBUG模式

+ 可以在通信中进行使用`bz2`或者`zlib`或者`lzma`进行数据压缩.

+ 请求可以设置Return字段,默认为True,表示要求返回响应为结果,如果设置为False,则不必返回任何结果,而是通过方法`system.getresult`获取结果

## 流程约定

### 连接建立

连接建立后无论是否有验证需求,客户端都会向服务器发送一条验证请求,

+ 如果服务端有验证信息,则会根据验证信息判断是否合法

    + 如果合法,那么返回一条信息用于响应验证请求
    + 如果不合法,那么返回验证错误

+ 如果服务端没有验证信息

    + 如果验证信息都为空,直接返回响应
    + 如果信息不为空,那么返回验证错误

如果验证未通过,客户端会抛出验证错误异常,如果验证通过了就可以继续发送其他请求

### 发送调用请求

验证请求通过后客户端才可以发送调用请求,请求接收后会检测

+ 函数是否被注册存在
+ 函数的参数是否与签名匹配

执行成功后会返回结果,失败则返回错误.而客户端收到结果后进行解析,如果是错误则解析出来抛出对应的错误

### 关闭连接

关闭连接有两种情况

+ 客户端主动关闭连接

    客户端应该在请求完毕后主动关闭连接.这并不需要额外的请求,直接关闭即可,服务器端收到EOF标识后会自动清理这个连接

+ 连接过期服务器关闭连接

    服务器每次写操作都会更新一个最近响应时间,如果长时间没有响应时间,则连接过期,服务器端主动关闭这个连接并向客户端发送一个超时错误.客户端收到超时错误消息后会抛出对应错误.默认的超时时间为180s
    
    如果想要一直保持连接,则需要客户端每隔一段时间发送一个心跳'ping'给服务器,服务器会响应'pong'同时刷新最近响应时间来避免超时.

## 数据形式约定

所有的出传输都以长连接的形式构建,没条请求以b`##PRO-END##`作为终止符

数据形式约定分为如下几个层次:

+ 传输数据类型和关键字格式约定

JSON可以表示四个基本类型(String、Numbers、Booleans和Null)和两个结构化类型(Objects和Arrays).而我们的message-pack也是以这6种基本类型为基础.

我们规定rpc注册的函数的参数和返回值也只能在这6种类型.且要求参数和返回值中的Object不允许嵌套

同时规定必须使用英文大写单词标识协议用到的字段,而协议预设的函数名也必须是大写.

+ 可以用于传输的对象约定

    我们约定合法的对象包括:
    + 验证请求对象
    + 自描述应答对象
    + 心跳请求与应答对象
    + 函数调用请求和响应对象
    + 异常/错误对象
    + 结果对象

+ 连接建立时客户端发送验证信息.

    成功建立连接后客户端会向服务发送一个验证请求,其形式为:
    ```json
    {
        "MPRPC":"0.1",// string 协议版本号
        "AUTH":{
            "USERNAME":xxx,//string
            "PASSWORD":xxx//string
        }
    }

    ```

+ 连接建立时服务端的自描述应答格式约定

    成功建立连接后服务器会收到验证请求,如果请求通过则会返回一个message-pack字节序列指明本rpc的基本信息,其形式为:
    ```json
    {
        "MPRPC":"0.1",// string 协议版本号
        "CODE":100,//指示允许访问
        "VERSION":"0.0.1",//string 服务的版本用于在客户端检验
        "DESC":"xxxx",// string 描述服务
        "DEBUG":true,// bool 是否使用debug模式,也就是传递的是json还是msgpack
        "COMPRESER":null,// enum 压缩算法,可选的有`bz2`,`zlib`,`lzma`和null
        "TIMEOUT":180,//number 设置的过期时间,设为0表示不设置过期时间
    }
    ```

    验证失败的话则会返回
    ```json
    {
        "MPRPC":"0.1",// string 协议版本号
        "CODE":501
    }
    ```

+ 客户端接收到错误后的行为

    客户端接收到错误后会先关闭连接然后抛出对应异常

+ 由客户端关闭连接后服务端的行为

    客户端关闭连接属于正常行为,没有额外动作

+ 心跳请求对象约定

    ```json
    {
        "MPRPC":"0.1",// string 协议版本号
        "HEARTBEAT":"ping"
    }
    ```

+ 心跳请求对象约定

    ```json
    {
        "MPRPC":"0.1",// string 协议版本号
        "CODE":101,
        "HEARTBEAT":"pong"
    }
    ```


+ 请求对象约定

    ```json
    {
        "MPRPC":"0.1",// string 协议版本号
        "ID":xxxx,//string 任务id
        "METHOD": xxx,//接收到要执行的函数名
        "RETURN":True,//默认为True,表示会返回结果,设置为False则表示不用返回结果,要结果的话可以用system.getresult获取
        "ARGS":xxx //(OPTION) list 接收到函数调用的参数,只允许为列表形式,如果有stream则无效
        "KWARGS":xxx //(OPTION) dict 接收到函数调用的参数,键值对的形式,如果有stream则无效
    }
    ```

+ 响应对象约定

    当发起一个rpc调用时，除通知之外，服务端都必须回复响应。响应表示为一个JSON对象，使用以下成员：

    ```json
    {
        "MPRPC":"0.1",// str 协议版本号
        "CODE":200,// number 响应码,响应码反应服务器状态,
        "MESSAGE": {} //(OPTION) object 对象为结果对象或者异常/错误对象
    }
    ```

    响应码含义表(参考自http协议)

    + 服务器回应,表述状态

    code|对应错误|意义
    ---|---|--
    100|---|表示初始的请求已经接受,客户应当继续发送请求的其余部分.
    101|---|表示响应为一个心跳

    + 正常响应

    code|对应错误|意义
    ---|---|--
    200|---|表示执行正常,返回的结果结束
    201|---|表示已经接受请求,且返回为一个流
    202|---|表示返回一个流的内容
    206|---|返回的流结束了

    + 过期警告

    code|对应错误|意义
    ---|---|--
    300|ExpireWarning|即将过期的函数执行正常
    301|ExpireStreamWarning|即将过期的函数,表示已经接受请求,且返回为一个流

    + method执行错误

    code|对应错误|意义
    ---|---|--
    400|RequestError|请求错误
    401|NotFindError|未找到对应的函数
    402|ParamError|请求的参数与签名不符
    403|RestrictAccessError|限制访问对应函数
    404|RPCRuntimeError|执行错误
    405|ResultLimitError|返回的结果超过限制的字节限制
    406|UnsupportSysMethodError|不支持的服务器固有方法

    + 服务器异常

    code|对应错误|意义
    ---|---|--
    500|RpcException|服务器异常
    501|LoginError|登录失败(口令有误)
    502|RequirementException|服务器的依赖服务异常,
    503|RpcUnavailableException|服务器不可用异常,一般是在维护
    504|TimeoutException|服务器连接超时异常
    505|ProtocolException|协议错误
    506|ProtocolSyntaxException|协议语法错误

    + 警告/错误异常对象约定

    针对任务的错误
    ```json
    {
        ID: xxx,// string 任务id
        EXCEPTION: xxx// string  服务器端错误/异常类型名
        MESSAGE: xxxx,// string or array or object 错误描述文字
        DATA: {//(OPTION) 错误的附加信息,由服务器决定,下面的是参考字段
            METHOD: //(OPTION)接收到要执行的函数名
            ARGS: //(OPTION)接收到函数调用的参数
            FRAME: //(OPTION)错误的帧信息
        }
    }
    ```
    服务器发出的错误没有message,直接通过错误码识别

    + 结果对象约定

    ```json
    {
        ID: xxx,// string 任务id
        RESULT: xxx// any  返回的结果
    }
    ```

### 服务器固有方法约定

+ system.listMethods()

    返回对外的函数接口

+ system.methodSignature(method:str)->obj

    返回指定函数的签名

+ system.methodHelp(method:str)->str

    返回对外的函数接口

+ system.lenConnections()->int:
    
    当前的连接总数

+ system.lenUndoneTasks()->int:
        
    当前还未完成的任务数

+ system.getresult(ID:str)->Any:

    获取某个ID对应的任务结果


### 客户端可设置参数:

+ host  主机
+ port  端口
+ auth  验证信息,默认为None
+ remote_version 远程服务的版本号,默认为None
+ heart_beat 默认为False

### 服务器可设置参数:

+ DEBUG 是否使用debug模式,默认为False
+ AUTH 验证信息,默认为None
+ COMPRESSION 使用什么进行压缩,默认为None
+ VERSION 服务的版本用于在客户端检验默认为None
+ DESC 描述服务的字符串,默认None,python实现可以直接返回对象的`__doc__`
+ TIMEOUT 多久没有请求就关闭连接默认为None
+ MPRPC 协议版本号,默认为最新

## 负载均衡方案(未定义)


### 定义中介的交互数据形式(未定义)

### 身份验证(未定义)

使用与服务器一致的身份验证.

请求:
```json
{
    "MPRPC":"0.1",// str 协议版本号
    "AUTH":{
            "USERNAME":xxx,//string
            "PASSWORD":xxx//string
        }
}
```

失败响应:

```json
{
    "MPRPC":"0.1",// str 协议版本号
    "CODE":51
}
```

成功响应:

```json
{
    "MPRPC":"0.1",// str 协议版本号
    "CODE":50,
    "URL":xxxxx
}
```

### 响应码含义表(参考自http协议)(未定义)

中介使用0~100间的状态码,其中0~50位请求码段,50~100为响应码段

code|对应错误|意义
---|---|--
50|---|验证通过
51|BrokerLoginError|验证失败