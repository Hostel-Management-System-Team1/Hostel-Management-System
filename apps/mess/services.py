from django.db import transaction

from apps.accounts.models import User


def publish_menu(menu_item, actor):
    """Publish a menu item by an authorized Mess Manager."""

    if actor.role != User.Role.MESS_MANAGER:
        raise PermissionError("Only Mess Managers can publish the menu.")

    with transaction.atomic():
        menu_item.published_by = actor
        menu_item.is_published = True
        menu_item.save()

    return menu_item
