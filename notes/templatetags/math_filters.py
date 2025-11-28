from django import template

register = template.Library()

@register.filter
def mul(a, b):
    try:
        return a * b
    except:
        return 0

@register.filter
def div(a, b):
    try:
        if b == 0:
            return 0
        return a / b
    except:
        return 0
