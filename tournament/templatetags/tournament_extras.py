from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Permite acceder a diccionarios en templates: {{ dict|get_item:key }}"""
    return dictionary.get(key)


@register.filter
def cop(value):
    """
    Formatea un número como pesos colombianos con separador de miles (punto).
    Ej: 12000 → '$12.000'  |  500 → '$500'
    """
    try:
        formatted = f'{int(value):,}'.replace(',', '.')
        return f'${formatted}'
    except (ValueError, TypeError):
        return value


@register.filter
def crd(value):
    """
    Formatea un número de créditos con separador de miles (punto).
    Ej: 16000 → '16.000'
    """
    try:
        return f'{int(value):,}'.replace(',', '.')
    except (ValueError, TypeError):
        return value


@register.simple_tag
def sandbox_stats():
    """Devuelve las estadísticas actuales del sandbox para usar en cualquier template."""
    from tournament.sandbox import sandbox_stats as _stats
    return _stats()


@register.filter
def multiply_by(value, arg):
    """Multiplica value por arg. Uso: {{ value|multiply_by:100 }}"""
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def divide_by(value, arg):
    """Divide value entre arg. Uso: {{ value|divide_by:max }}"""
    try:
        return int(value) // int(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0


@register.filter
def add(value, arg):
    """Suma dos valores. Uso: {{ a|add:b }}"""
    try:
        return int(value) + int(arg)
    except (ValueError, TypeError):
        return 0
