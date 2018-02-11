from typing import Any


def resolve_dotted_attribute(obj, attr, allow_dotted_names=True):
    """将一个`.`属性名称解析为一个对象.

    `resolve_dotted_attribute(a, 'b.c.d') => a.b.c.d`.
    如果链中的任何属性以`_`开始,则引发AttributeError.

    Parameters:

        obj (Any): - 要执行的对象
        attr (str): - 调用链的字符串形式
        allow_dotted_names (bool): - 默认为True,
        如果可选的allow_dotted_names参数为false,则不支持点,此功能与`getattr(obj，attr)`类似.

    Returns:

        (List[str]): - 所有对象中的公开的方法名

    """

    if allow_dotted_names:
        attrs = attr.split('.')
    else:
        attrs = [attr]

    for i in attrs:
        if i.startswith('_'):
            raise AttributeError(
                'attempt to access private attribute "%s"' % i
            )
        else:
            obj = getattr(obj, i)
    return obj


def list_public_methods(obj: Any):
    """找出对象中的函数.

    Parameters:

        obj (Any): - 要执行的对象

    Returns:

        (List[str]): - 所有对象中的公开的方法名

    """
    return [member for member in dir(obj)
            if not member.startswith('_') and
            callable(getattr(obj, member))]
