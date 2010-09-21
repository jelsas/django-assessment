from django.conf.urls.defaults import *
from assessment.models import *
from django.contrib.auth.models import User

from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('assessment.views',
  # Viewing assessor's assigned and available queries
  url(r'^assessor/dashboard/$', 'assessor_dashboard', name='dashboard'),

  # Viewing overall assessment progress
  url(r'^admin/dashboard/$', 'admin_dashboard', name='admin_dashboard'),

  # Uploading data
  url(r'^admin/upload_data/$', 'upload_data', name='upload_data'),

  # Downloading data
  url(r'^admin/download_data/$', 'download_data', name='download_data'),

  # Confirming query assignment
  url(r'^assessor/selectquery/(?P<query_id>\d+)/$', 'select_query_confirm',
    name='select_query_confirm'),

  # Assignment viewing
  url(r'^assessor/assignment/(?P<assignment_id>\d+)/$', 'assignment_detail',
    name='assignment_detail'),

  # Getting the next assessment
  url(r'^assessor/assignment/(?P<assignment_id>\d+)/next/$',
    'next_assessment', name='next_assessment'),

  # Performing a new assessment.  The URL describes the information in
  # the assessment.selection_strategies.DocumentPairPresentation
  url(r'^assessor/assignment/(?P<assignment_id>\d+)/' + \
                       '(?P<left_doc>\d+)(?P<left_fixed>\+?)/' + \
                       '(?P<right_doc>\d+)(?P<right_fixed>\+?)/$',
    'new_assessment', name='new_assessment'),

  # Assessment viewing
  url(r'^assessor/assessment/(?P<assessment_id>\d+)/$',
    'assessment_detail', name='assessment_detail'),

  # Entering the information need
  url(r'^assessor/assignment/(?P<assignment_id>\d+)/infoneed/$',
    'information_need', name='information_need'),

  # Entering a comment
  url(r'^assessor/comment/$', 'comment', name='comment'),

  # all other URLs go to the dashboard
  (r'.*', 'redirect_to_pagename', {'pagename': 'dashboard'}),
)
