from django.conf import settings

# A string format pattern with a placeholder (%s) for the document identifier
DOCSERVER_URL_PATTERN = getattr(settings, 'DOCSERVER_URL_PATTERN',
  'http://example.com/document_server.php?docid=%s')

# Is a new registration required to provide a validation key?
REGISTRATION_KEY = getattr(settings, 'REGISTRATION_KEY', None)

# number of assessments per query
ASSESSMENTS_PER_QUERY = getattr(settings, 'ASSESSMENTS_PER_QUERY', 25)

