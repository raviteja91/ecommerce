from __future__ import unicode_literals

import hashlib

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from oscar.core.loading import get_model
from rest_framework import status, viewsets
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from ecommerce.courses.models import Course
from ecommerce.extensions.api.serializers import ConditionalOfferSerialitzer
from ecommerce.extensions.catalogue.models import Catalog

ConditionalOffer = get_model('offer', 'ConditionalOffer')
Condition = get_model('offer', 'Condition')
Benefit = get_model('offer', 'Benefit')
Product = get_model('catalogue', 'Product')
Range = get_model('offer', 'Range')
StockRecord = get_model('partner', 'StockRecord')


class OfferViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated, IsAdminUser)
    queryset = ConditionalOffer.objects.filter(offer_type=ConditionalOffer.SITE)
    serializer_class = ConditionalOfferSerialitzer

    def create(self, request, *args, **kwargs):
        with transaction.atomic():
            program_uuid = request.data['program_uuid']
            program = self.get_program(program_uuid)
            _range = self.create_range(program)
            benefit = Benefit.objects.create(
                range=_range,
                type=Benefit.PERCENTAGE,
                value=request.data['benefit_value']
            )
            condition = Condition.objects.create(
                range=_range,
                type=Condition.COVERAGE,
                value=_range.catalog.stock_records.count()
            )

            offer = ConditionalOffer.objects.create(
                name='Program: {}'.format(program['title']),
                offer_type=ConditionalOffer.SITE,
                benefit=benefit,
                condition=condition,
                start_datetime=request.data['start_datetime'],
                end_datetime=request.data['end_datetime']
            )

            return Response(self.serializer_class(offer).data, status=status.HTTP_201)

    def get_program(self, program_uuid):
        cache_key = hashlib.md5(
            'program_{uuid}'.format(uuid=program_uuid)
        ).hexdigest()
        program = cache.get(cache_key)
        if not program:
            api = self.request.site.siteconfiguration.course_catalog_api_client
            program = api.programs(program_uuid).get()
            cache.set(cache_key, program, settings.PROGRAM_CACHE_TIMEOUT)
        return program

    def create_range(self, program):
        """ Create an Oscar Range for the program. """
        stock_records = []
        seat_types = program['applicable_seat_types']
        for course in program['courses']:
            for course_run in course['course_runs']:
                course_ = Course.objects.get(id=course_run['key'])
                seat = course_.seat_products.get(
                    attributes__name='certificate_type',
                    attribute_values__value_text__in=seat_types
                )
                stock_records.append(StockRecord.objects.get(product=seat))

        name = 'Program: {}'.format(program['title'])
        catalog = Catalog.objects.create(
            name=name,
            partner=self.request.site.siteconfiguration.partner
        )

        catalog.stock_records.add(*stock_records)
        return Range.objects.create(
            name=name,
            catalog=catalog
        )
