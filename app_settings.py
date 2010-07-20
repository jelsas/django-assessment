from django.conf import settings


# A string format pattern with a placeholder (%s) for the document identifier
EXTERNAL_URL_PATTERN = getattr(settings, 'EXTERNAL_URL_PATTERN',
  'http://manchester.lti.cs.cmu.edu/testing/showdoc.php?documentID=%s')

# Should the left & right documents be swapped randomly when presented?
RANDOMIZE_DOC_PRESENTATION = getattr(settings, 'RANDOMIZE_DOC_PRESENTATION',
                                     True)

# Is a new registration required to provide a validation key?
REGISTRATION_KEY = getattr(settings, 'REGISTRATION_KEY', None)


