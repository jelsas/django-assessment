from django.conf import settings

# A string format pattern with a placeholder (%s) for the document identifier
DOCSERVER_URL_PATTERN = getattr(settings, 'DOCSERVER_URL_PATTERN',
  'http://example.com/document_server.php?docid=%s')

# Is a new registration required to provide a validation key?
REGISTRATION_KEY = getattr(settings, 'REGISTRATION_KEY', None)

# number of assessments per query
ASSESSMENTS_PER_QUERY = getattr(settings, 'ASSESSMENTS_PER_QUERY', 25)

# max number of assessments per document
MAX_ASSESSMENTS_PER_DOC = getattr(settings, 'MAX_ASSESSMENTS_PER_DOC', -1)

# should we provide a "why?" option?
COLLECT_PREFERENCE_REASON = getattr(settings, 'COLLECT_PREFERENCE_REASON',
                                      False)

# should we collect an information need statement?
COLLECT_INFORMATION_NEED = getattr(settings, 'COLLECT_INFORMATION_NEED',
                                   True)

# Do we assume judgements are transitivie?
ASSUME_TRANSITIVITY = getattr(settings, 'ASSUME_TRANSITIVITY', False)
