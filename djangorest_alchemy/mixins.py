# -*- coding: utf-8 -*-

import six
from django.core.paginator import InvalidPage, Page, Paginator
from rest_framework import status
from rest_framework.response import Response


STATUS_CODES = {
    'created': status.HTTP_201_CREATED,
    'updated': status.HTTP_200_OK,
    'accepted': status.HTTP_202_ACCEPTED
}


class MultipleObjectMixin(object):
    """SQLAlchemy analog to Django's MultipleObjectMixin."""
    allow_empty = True
    query_object = None
    paginate_by = None
    paginator_class = Paginator

    def filter_query_object(self, query_object):
        """Generic filtering.

        This is a stub and has yet to be implemented.
        """
        return query_object

    def paginate_query_object(self, query_object, page_size):
        """Paginate the query object."""
        paginator = self.get_paginator(
            query_object, page_size,
            allow_empty_first_page=self.get_allow_empty())
        page = self.kwargs.get('page') or self.request.GET.get('page') or 1
        try:
            page_number = int(page)
        except ValueError:
            if page == 'last':
                page_number = paginator.num_pages
            else:
                raise InvalidPage("Page is not 'last', "
                                  "nor can it be converted to an int.")

        # DB2 fix for invalid 0 literal.
        # Generates FETCH 0 rows if not done this way
        if not paginator.count == 0:
            page = paginator.page(page_number)
            return (paginator, page, page.object_list, page.has_other_pages())
        else:
            return (paginator, Page([], 1, paginator), [], False)

    def get_paginate_by(self, query_object):
        """Get the number of items to paginate by. None for no pagination."""
        return self.paginate_by

    def get_paginator(self, query_object, per_page, orphans=0,
                      allow_empty_first_page=True):
        """Get a paginator instance.

        The class used is overridable by setting the paginator_class
        attribute.
        """
        return self.paginator_class(
            query_object, per_page, orphans=orphans,
            allow_empty_first_page=allow_empty_first_page)

    def get_allow_empty(self):
        """Returns True to display empty lists, False to 404."""
        return self.allow_empty

    def get_page(self, queryset):
        """Add the object list to the template context."""
        page_size = self.get_paginate_by(queryset)

        query_object = self.filter_query_object(queryset)

        paginator, page, query_object, is_paginated = \
            self.paginate_query_object(query_object, page_size)

        return query_object


def make_action_method(name, methods, **kwargs):
    def func(self, request, pk=None, **kwargs):
        assert hasattr(request, 'data'), 'request object must have data'
        ' attribute'
        assert hasattr(self, 'manager_class'), 'viewset must have'
        ' manager_class defined'
        assert hasattr(self, 'manager_factory'), 'viewset must provide a'
        ' manager_factory method to insantiate the manager'

        mgr = self.manager_factory(context={'request': request})
        mgr_method = getattr(mgr, name)

        resp = mgr_method(request.data, pk, **kwargs)

        # no response returned back, assume everything is fine
        if not resp:
            return Response(resp, status.HTTP_200_OK)

        return Response(resp, STATUS_CODES[resp['status']])

    func.bind_to_methods = methods
    func.kwargs = kwargs

    return func


class ManagerMeta(type):
    """
    Meta class to read action methods from
    manager and attach them to viewset
    This allows us to directly call manager methods
    without writing any action methods on viewsets
    """
    def __new__(cls, name, bases, attrs):
        if 'manager_class' in attrs:
            mgr_class = attrs['manager_class']
            if hasattr(mgr_class, 'action_methods'):
                for mname, methods in mgr_class.action_methods.items():
                    attrs[mname] = make_action_method(mname.lower(), methods)

        return super(ManagerMeta, cls).__new__(cls, name, bases, attrs)


class ManagerMixin(six.with_metaclass(ManagerMeta, object)):
    """
    Manager mixin allows to use a manager class
    to provide the actual CRUD implementation in
    addition to providing action methods

    Example::

        class MyManager(AlchemyModelManager):
            action_methods = {'my_method': ['POST']}

            def my_method(self, data, pk=None, **kwargs):
                # data is actual payload
                return {'status': 'created'}

        class MyViewSet(viewset.Viewsets, ManagerMixin):
            manager_class = MyManager
    """

    def manager_factory(self, *args, **kwargs):
        '''
        Factory method for instantiating manager class
        Override to return back your instance
        '''
        assert hasattr(self, 'manager_class'), \
            "manager_class has to be specified"
        return self.manager_class(*args, **kwargs)
