from assessment.models import *
from django.contrib import admin

class PreferenceAssessmentReasonInline(admin.TabularInline):
  model = PreferenceAssessmentReason

class QueryDocPairInline(admin.TabularInline):
  model = QueryDocumentPair
  extra = 10

admin.site.register(Query,
  list_display = ('qid', 'text', 'remaining_assignments'),
  inlines = [QueryDocPairInline],
  short_description = "Queries and Doc Pairs")

admin.site.register(PreferenceAssessment,
  list_display = ('assignment', 'query_doc_pair', 'preference', 'reasons_str',
                  'created_date'),
  inlines = [PreferenceAssessmentReasonInline])

admin.site.register(Assignment,
  list_display = ('assessor', 'query', 'created_date', 'status',
                  'elapsed_time'))

admin.site.register(PreferenceReason,
  list_display = ('short_name', 'description', 'active'))

admin.site.register(Comment)
