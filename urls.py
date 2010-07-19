from django.conf.urls.defaults import *
from assessment.models import *
from django.contrib.auth.models import User

from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('assessment.views',
  url(r'^assessor/dashboard/$', 'assessor_dashboard', name='dashboard'),

  # Confirming query assignment
  url(r'^assessor/selectquery/(?P<query_id>\d+)/$', 'select_query_confirm',
    name='select_query_confirm'),

  # Assignment viewing
  url(r'^assessor/assignment/(?P<assignment_id>\d+)/$', 'assignment_detail',
    name='assignment_detail'),

  # Getting the next assessment
  url(r'^assessor/assignment/(?P<assignment_id>\d+)/next/$',
    'next_assessment', name='next_assessment'),

  # Creating a new assessment for a docpair
  url(r'^assessor/assignment/(?P<assignment_id>\d+)/'+
                            '(?P<querydocumentpair_id>\d+)/$',
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
