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
