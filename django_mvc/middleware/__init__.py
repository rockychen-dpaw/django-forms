from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed

class AddContextVarMiddleware(object):
    def __init__(self,get_response):
        self.get_response = get_response
        if not hasattr(settings,"ADD_CONTEXT_VARS"):
            raise MiddlewareNotUsed("settings doesn't declare method ADD_CONTEXT_VARS(response,context_data).")

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_template_response(self, request,response):
        settings.ADD_CONTEXT_VARS(request,response.context_data)
        return response
