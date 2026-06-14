from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('help-center/', views.help_center, name='help_center'),
    path('careers/', views.careers, name='careers'),
    path('faq/', views.faq, name='faq'),
    path('roadmap/', views.roadmap, name='roadmap'),
    path('legal-docs/', views.legal, name='legal'),
    path('education/', views.education, name='education'),
]