from django.core.urlresolvers import reverse

from ecommerce.courses.tests.mixins import CourseCatalogServiceMockMixin
from ecommerce.tests.testcases import TestCase


class OfferViewSetTests(CourseCatalogServiceMockMixin, TestCase):
    path = reverse('api:v2:offers-list')

    def setUp(self):
        super(OfferViewSetTests, self).setUp()
        self.user = self.create_user(is_staff=True)
        self.client.login(username=self.user.username, password=self.password)

    def test_authentication_required(self):
        """Guest cannot access the view."""
        self.client.logout()
        response = self.client.post(self.path, data={})
        self.assertEqual(response.status_code, 401)

    def test_authorization_required(self):
        """Non-staff user cannot access the view."""
        user = self.create_user(is_staff=False)
        self.client.login(username=user.username, password=self.password)
        response = self.client.post(self.path, data={})
        self.assertEqual(response.status_code, 403)

    def test_create(self):
        """New ConditionalOffer is created."""
        data = {
            'program_uuid': 123,
            'benefit_value': 15,
        }
        self.request.data = data
        self.mock_catalog_program_list()
        response = self.client.post(self.path, data=data)
