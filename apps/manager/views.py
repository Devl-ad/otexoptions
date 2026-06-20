from django.shortcuts import render
from .decorator import manager_required


@manager_required
def index(request):
    return render(request, "manager/index.html")
