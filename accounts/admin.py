# O admin.site.register() padrão do Django só funciona com models do
# django.db.models (banco relacional). Como Usuario é um Document do
# MongoEngine, ele não aparece automaticamente no /admin/.
#
# Se mais pra frente vocês quiserem visualizar/editar usuários pelo admin,
# o pacote "django-mongoengine" oferece um ModelAdmin compatível. Por
# enquanto, o endpoint /status/mongo/ (core/views.py) já serve para
# conferir rapidamente o que está salvo no banco durante o desenvolvimento.
