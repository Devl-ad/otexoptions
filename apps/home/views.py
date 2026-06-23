from django.shortcuts import render


def home(request):
    return render(request, "index.html")


def about(request):
    return render(request, "about.html")


def contact(request):
    return render(request, "contacts.html")


def help_center(request):
    return render(request, "help_center.html")


def careers(request):
    return render(request, "careers.html")


def faq(request):
    return render(request, "faq.html")


def roadmap(request):
    return render(request, "roadmap.html")


def legal(request):
    return render(request, "legal-docs.html")


def education(request):
    return render(request, "education.html")


def privacy(request):
    return render(request, "privacy.html")
