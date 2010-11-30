from assessment.models import *
from django.contrib import admin

class PreferenceAssessmentReasonInline(admin.TabularInline):
  model = PreferenceReason

class DocInline(admin.TabularInline):
  model = Document
  extra = 10

admin.site.register(Query,
  list_display = ('qid', 'text', 'remaining_assignments'),
  inlines = [DocInline],
  short_description = "Queries and Documents")

class AssessedDocumentRelationAdmin(admin.ModelAdmin):
  list_display = ('query', 'assessor',
                  'source_docname', 'target_docname',
                  'relation_type_as_permalink')
  list_filter = ('source_doc__assignment__query',
                 'source_doc__assignment__assessor',
                 'relation_type',)
admin.site.register(AssessedDocumentRelation, AssessedDocumentRelationAdmin)

admin.site.register(Assignment,
  list_display = ('assessor', 'query', 'created_date',
                  'num_assessments_complete', 'elapsed_time'))

admin.site.register(PreferenceReason,
  list_display = ('short_name', 'description', 'active'))

admin.site.register(Comment)

admin.site.register(AssessedDocument,
  list_display = ('id', 'document', 'assignment'))
