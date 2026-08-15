"""CMS integrations — ROADMAP.md's "CMS push/pull content API".

app/core/integrations/base.py     — CMSIntegration ABC, the provider contract
app/core/integrations/strapi.py   — StrapiIntegration, the first working provider
app/core/integrations/factory.py  — get_cms_integration(provider), same
                                     "one active provider, selectable, more
                                     can be added later" shape as
                                     app/core/translation_backends.py
app/core/cms_service.py           — orchestration: push/pull + provenance +
                                     DeploymentRecord bookkeeping
"""
