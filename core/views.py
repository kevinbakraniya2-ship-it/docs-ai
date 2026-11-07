from django.shortcuts import render


def home(request):
    """Show the Docs AI starting page."""
    return render(request, "core/home.html")
