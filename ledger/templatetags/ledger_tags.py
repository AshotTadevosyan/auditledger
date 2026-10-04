from django import template
from django.urls import reverse
from ..models import MODELS
register = template.Library()

@register.filter
def human(value):
    return str(value or '').replace('_', ' ').capitalize()

@register.filter
def event_url(event):
    model = MODELS.get(event.entity_type)
    if not model or not model.objects.filter(pk=event.entity_id).exists():
        return ''
    if event.entity_type == 'engagement':
        return reverse('overview', args=[event.engagement_id])
    return reverse('detail', args=[event.engagement_id, event.entity_type, event.entity_id])
