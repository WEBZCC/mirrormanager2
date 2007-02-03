from turbogears.identity.exceptions import IdentityFailure
import logging
import cherrypy


import turbogears
from turbogears import controllers, expose, validate, redirect, widgets, validators, error_handler, exception_handler
from turbogears import identity
from tgfastdata import DataController
import sqlobject
from sqlobject.sqlbuilder import *

from mirrors import json
from mirrors import my_validators
from mirrors.model import *
from mirrors.lib import createErrorString


log = logging.getLogger("mirrors.controllers")

# From the TurboGears book
class content:
    @turbogears.expose()
    def default(self, *vpath, **params):
        if len(vpath) == 1:
            identifier = vpath[0]
            action = self.read
            verb = 'read'
        elif len(vpath) == 2:
            identifier, verb = vpath
            verb = verb.replace('.','_')
            action = getattr(self, verb, None)
            if not action:
                raise cherrypy.NotFound
            if not action.exposed:
                raise cherrypy.NotFound
        else:
            raise cherrypy.NotFound


        if verb == "new":
            return action(**params)
        elif verb == "create":
            return action(**params)
        else:
            try:
                item=self.get(identifier)
            except sqlobject.SQLObjectNotFound:
                raise cherrypy.NotFound

            return action(item['values'], **params)




def is_siteadmin(site, identity):
    if identity.in_group("admin"):
        return True
    
    for a in site.admins:
        if a.username == identity.current.user_name:
            return True
    return False

class SiteFields(widgets.WidgetsList):
    name     = widgets.TextField(validator=validators.NotEmpty)
    password = widgets.TextField(validator=validators.NotEmpty)
    orgUrl   = widgets.TextField(label="Organization URL", validator=validators.URL)
    private  = widgets.CheckBox()
    admin_active = widgets.CheckBox("admin_active",default=True)
    user_active = widgets.CheckBox(default=True)


site_form = widgets.TableForm(fields=SiteFields(),
                              submit_text="Save Site")


class SiteController(controllers.Controller, content):
    require = identity.not_anonymous()

    def get(self, id):
        return dict(values=Site.get(id))
    
    @expose(template="mirrors.templates.site")
    def read(self, site):
        if not is_siteadmin(site, identity):
            turbogears.flash("Error:You are not an admin for Site %s" % site.name)
            raise turbogears.redirect("/")
        submit_action = "/site/%s/update" % site.id
        return dict(form=site_form, values=site, action=submit_action)

    @expose(template="mirrors.templates.site")
    def new(self, **kwargs):
        submit_action = "/site/0/create"
        return dict(form=site_form, values=None, action=submit_action)
    
    @expose(template="mirrors.templates.site")
    @error_handler(new)
    @validate(form=site_form)
    def create(self, **kwargs):
        try:
            if not identity.in_group("admin") and kwargs.has_key('admin_active'):
                del kwargs['admin_active']
            site = Site(**kwargs)
            id = site.id
            SiteAdmin(site=site, username=identity.current.user_name)
            submit_action = "/site/%s/update" % id
        except: # probably sqlite IntegrityError but we can't catch that for some reason... 
            turbogears.flash("Error:Site %s already exists" % kwargs['name'])
            submit_action = "/site/0/create"
        raise turbogears.redirect("/")

    @expose(template="mirrors.templates.site")
    @validate(form=site_form)
    def update(self, site, **kwargs):
        if not is_siteadmin(site, identity):
            turbogears.flash("Error:You are not an admin for Site %s" % site.name)
            raise redirect("/")
        if not identity.in_group("admin") and kwargs.has_key('admin_active'):
            del kwargs['admin_active']
        site.set(**kwargs)
        site.sync()
        turbogears.flash("Site Updated")
        raise turbogears.redirect("/")

    @expose(template="mirrors.templates.site")
    def delete(self, site, **kwargs):
        if not is_siteadmin(site, identity):
            turbogears.flash("Error:You are not an admin for Site %s" % site.name)
            raise turbogears.redirect("/")

        site.destroySelf()
        raise turbogears.redirect("/")



class SiteAdminFields(widgets.WidgetsList):
    username = widgets.TextField(validator=validators.NotEmpty)


siteadmin_form = widgets.TableForm(fields=SiteAdminFields(),
                              submit_text="Create Site Admin")


class SiteAdminController(controllers.Controller, content):
    require = identity.not_anonymous()

    def get(self, id):
        return dict(values=SiteAdmin.get(id))
    
    @expose(template="mirrors.templates.boringform")
    def new(self, **kwargs):
        siteid=kwargs['siteid']
        try:
            site = Site.get(siteid)
        except sqlobject.SQLObjectNotFound:
            raise redirect("/")

        if not is_siteadmin(site, identity):
            turbogears.flash("Error:You are not an admin for Site %s" % site.name)
            raise redirect("/")
            
        submit_action = "/siteadmin/0/create?siteid=%s" % siteid
        return dict(form=siteadmin_form, values=None, action=submit_action, title="New Site Admin")
    
    @expose(template="mirrors.templates.siteadmin")
    @error_handler(new)
    @validate(form=siteadmin_form)
    def create(self, **kwargs):
        if not kwargs.has_key('siteid'):
            turbogears.flash("Error: form didn't provide siteid")
            raise redirect("/")
        siteid = kwargs['siteid']

        try:
            site = Site.get(siteid)
        except sqlobject.SQLObjectNotFound:
            turbogears.flash("Error: Site %s does not exist" % siteid)
            raise redirect("/")

        if not is_siteadmin(site, identity):
            turbogears.flash("Error:You are not an admin for Site %s" % site.name)
            raise redirect("/")
            
        username = kwargs['username']
        try:
            siteadmin = SiteAdmin(site=site, username=username)
        except: # probably sqlite IntegrityError but we can't catch that for some reason... 
            turbogears.flash("Error:SiteAdmin %s already exists" % kwargs['username'])
        raise turbogears.redirect("/site/%s" % siteid)

    @expose(template="mirrors.templates.siteadmin")
    def delete(self, siteadmin, **kwargs):
        site = siteadmin.site
        if not is_siteadmin(site, identity):
            turbogears.flash("Error:You are not an admin for Site %s" % site.name)
            raise turbogears.redirect("/")

        siteadmin.destroySelf()
        raise turbogears.redirect("/site/%s" % site.id)


class HostFields(widgets.WidgetsList):
    admin_active = widgets.CheckBox("admin_active")
    user_active = widgets.CheckBox()
    country = widgets.TextField(validator=validators.NotEmpty)
    private = widgets.CheckBox()
    private_rsync_url = widgets.TextField()
    robot_email = widgets.TextField(validator=validators.Email)
    


host_form = widgets.TableForm(fields=HostFields(),
                              submit_text="Save Host")

class HostController(controllers.Controller, content):
    require = identity.not_anonymous()

    def get(self, id):
        return dict(values=Host.get(id))

    @expose(template="mirrors.templates.host")
    def read(self, host):
        site = host.site
        if not is_siteadmin(site, identity):
            turbogears.flash("Error:You are not an admin for Site %s" % site.name)
            raise turbogears.redirect("/")
        submit_action = "/host/%s/update" % host.id
        return dict(form=host_form, values=host, action=submit_action, acl_ips=host.acl_ips)

    @expose(template="mirrors.templates.host")
    @validate(form=host_form)
    def update(self, host, **kwargs):
        site = host.site
        if not is_siteadmin(site, identity):
            turbogears.flash("Error:You are not an admin for Site %s" % site.name)
            raise redirect("/")
        if not identity.in_group("admin") and kwargs.has_key('admin_active'):
            del kwargs['admin_active']
        host.set(**kwargs)
        host.sync()
        turbogears.flash("Host Updated")
        raise turbogears.redirect("/")

    @expose()
    def delete(self, host, **kwargs):
        site = host.site
        if not is_siteadmin(site, identity):
            turbogears.flash("Error:You are not an admin for Site %s" % site.name)
            raise turbogears.redirect("/")

        host.destroySelf()
        raise turbogears.redirect("/")


##################################################################33
# HostCategory
##################################################################33
class HostCategoryFields(widgets.WidgetsList):
    category = widgets.SingleSelectField(options = [(c.id, c.name) for c in Category.select()])
    enabled = widgets.CheckBox(default=True)
    path = widgets.TextField(validator=validators.NotEmpty)
    upstream = widgets.TextField(validator=validators.URL)

host_category_form = widgets.TableForm(fields=HostCategoryFields(),
                                       submit_text="Save Host Category")



class HostCategoryController(controllers.Controller, content):
    require = identity.not_anonymous()

    def get(self, id):
        return dict(values=HostCategory.get(id))

    @expose(template="mirrors.templates.hostcategory")
    def new(self, **kwargs):
        try:
            hostid=kwargs['hostid']
            host = Host.get(hostid)
        except sqlobject.SQLObjectNotFound:
            raise redirect("/")
        submit_action = "/host_category/0/create?hostid=%s" % hostid
        return dict(form=host_category_form, values=None, action=submit_action)
    
    
    @expose(template="mirrors.templates.hostcategory")
    def read(self, hostcategory):
        host = hostcategory.host
        site = host.site
        if not is_siteadmin(site, identity):
            turbogears.flash("Error:You are not an admin for Site %s" % site.name)
            raise turbogears.redirect("/")
        submit_action = "/host_category/%s/update" % hostcategory.id
        return dict(form=host_category_form, values=hostcategory, action=submit_action)

    @expose(template="mirrors.templates.hostcategory")
    @error_handler(new)
    @validate(form=host_category_form)
    def create(self, **kwargs):
        if not kwargs.has_key('hostid'):
            turbogears.flash("Error: form didn't provide hostid")
            raise redirect("/")
        hostid = kwargs['hostid']
        del kwargs['hostid']
        host = Host.get(hostid)
        category = Category.get(kwargs['category'])
        del kwargs['category']
#            submit_action = "/host_category/%s/update" % id
        try:
            hostcategory = HostCategory(host=host, category=category, **kwargs)
        except:
            turbogears.flash("Error: Host already has category %s.  Try again." % category.name)
#            submit_action = "/host_category/0/create"
            raise turbogears.redirect("/host_category/0/create?hostid=%s" % hostid)
        raise turbogears.redirect("/host/%s" % hostid)


    @expose(template="mirrors.templates.hostcategory")
    @validate(form=host_category_form)
    def update(self, hostcategory, **kwargs):
        host = hostcategory.host
        site = host.site
        if not is_siteadmin(site, identity):
            turbogears.flash("Error:You are not an admin for Site %s" % site.name)
            raise redirect("/")
        hostcategory.set(**kwargs)
        hostcategory.sync()
        turbogears.flash("HostCategory Updated")
        raise turbogears.redirect("/")

    @expose(template="mirrors.templates.hostcategory")
    def delete(self, hostcategory, **kwargs):
        host = hostcategory.host
        site = host.site
        if not is_siteadmin(site, identity):
            turbogears.flash("Error:You are not an admin for Site %s" % site.name)
            raise turbogears.redirect("/")

        hostcategory.destroySelf()
        raise turbogears.redirect("/host/%s" % host.id)


class HostListitemController(controllers.Controller, content):
    require = identity.not_anonymous()
    title = ""
    form = None

    def get(self, id):
        return self.do_get(id)
    
    @expose(template="mirrors.templates.boringform")
    def new(self, **kwargs):
        try:
            hostid=kwargs['hostid']
            host = Host.get(hostid)
        except sqlobject.SQLObjectNotFound:
            raise redirect("/")

        site = host.site
        if not is_siteadmin(site, identity):
            turbogears.flash("Error:You are not an admin for Site %s" % site.name)
            raise redirect("/")
            
        submit_action = "%s/0/create?hostid=%s" % (self.submit_action_prefix, hostid)
        return dict(form=self.form, values=None, action=submit_action, title=self.title)
    
    @expose(template="mirrors.templates.boringform")
    @error_handler(new)
    @validate(form=form)
    def create(self, **kwargs):
        if not kwargs.has_key('hostid'):
            turbogears.flash("Error: form didn't provide siteid")
            raise redirect("/")
        hostid = kwargs['hostid']

        try:
            host = Host.get(hostid)
        except sqlobject.SQLObjectNotFound:
            turbogears.flash("Error: Host %s does not exist" % hostid)
            raise redirect("/")

        site = host.site
        if not is_siteadmin(site, identity):
            turbogears.flash("Error:You are not an admin for Site %s" % site.name)
            raise redirect("/")
            

        try:
            self.do_create(host, kwargs)
        except: # probably sqlite IntegrityError but we can't catch that for some reason... 
            turbogears.flash("Error: entity already exists")
        raise turbogears.redirect("/host/%s" % host.id)

    @expose(template="mirrors.templates.boringform")
    def delete(self, thing, **kwargs):
        host = thing.host
        site = host.site
        if not is_siteadmin(site, identity):
            turbogears.flash("Error:You are not an admin for Site %s" % site.name)
            raise turbogears.redirect("/")

        thing.destroySelf()
        raise turbogears.redirect("/host/%s" % host.id)



class HostAclIPFields(widgets.WidgetsList):
    ip = widgets.TextField(label="IP", validator=validators.NotEmpty)

host_acl_ip_form = widgets.TableForm(fields=HostAclIPFields(),
                                     submit_text="Create Host ACL IP")

class HostAclIPController(HostListitemController):
    submit_action_prefix="/host_acl_ip"
    title = "New Host ACL IP"
    form = host_acl_ip_form

    def do_get(self, id):
        return dict(values=HostAclIP.get(id))

    def do_create(self, host, kwargs):
        HostAclIP(host=host, ip=kwargs['ip'])



class HostNetblockFields(widgets.WidgetsList):
    netblock = widgets.TextField(validator=validators.NotEmpty)

host_netblock_form = widgets.TableForm(fields=HostNetblockFields(),
                                       submit_text="Create Host Netblock")

class HostNetblockController(HostListitemController):
    submit_action_prefix="/host_netblock"
    title = "New Host Netblock"
    form = host_netblock_form

    def do_get(self, id):
        return dict(values=HostNetblock.get(id))

    def do_create(self, host, kwargs):
        HostNetblock(host=host, netblock=kwargs['netblock'])

class HostCountryAllowedFields(widgets.WidgetsList):
    country = widgets.TextField(validator=validators.NotEmpty)

host_country_allowed_form = widgets.TableForm(fields=HostCountryAllowedFields(),
                                              submit_text="Create Country Allowed")

class HostCountryAllowedController(HostListitemController):
    submit_action_prefix="/host_country_allowed"
    title = "New Host Country Allowed"
    form = host_country_allowed_form

    def do_get(self, id):
        return dict(values=HostCountryAllowed.get(id))

    def do_create(self, host, kwargs):
        HostCountryAllowed(host=host, country=kwargs['country'])




# This exports the /pub/fedora/linux/core/... directory tree.
# For each directory requested, it returns the mirrors of that directory.

class PubController(controllers.Controller):
    @expose(template="mirrors.templates.mirrorlist", format="plain", content_type="text/plain")
    def default(self, *vpath, **params):
        path = 'pub/' + '/'.join(vpath)
        country = None
        if params.has_key('country'):
            country = params['country']
        urls = directory_mirror_urls(path, country=country)
        for u in urls:
            if not u.startswith('http://') and not u.startswith('ftp://'):
                urls.remove(u)
        return dict(values=urls)

        

class Root(controllers.RootController, content):
    site = SiteController()
    siteadmin = SiteAdminController()
    host = HostController()
    pub = PubController()
    host_country_allowed = HostCountryAllowedController()
    host_acl_ip = HostAclIPController()
    host_netblock = HostNetblockController()
    host_category = HostCategoryController()
    
    @expose(template="mirrors.templates.welcome")
    @identity.require(identity.in_any_group("admin", "user"))
    def index(self):
        if "admin" in identity.current.groups:
            sites = Site.select()
        else:
            sites = Site.select(join=INNERJOINOn(Site, SiteAdmin, AND(SiteAdmin.q.siteID == Site.q.id,
                                                                      SiteAdmin.q.username == identity.current.user_name)))

            
        if "admin" in identity.current.groups:
            return {"sites":sites,
                    "arches":Arch.select(),
                    "products":Product.select(),
                    "versions":Version.select(),
                    "directories":Directory.select(),
                    "categories":Category.select(),
                    "repositories":Repository.select(),
                    }
        else:
            return {"sites":sites}

    @expose(template="mirrors.templates.rsync_acl", format="plain", content_type="text/plain")
    def rsync_acl(self):
        rsync_acl_list = []
        for h in Host.select():
            if h.is_active():
                n = h.acl_ips
                if n is not None:
                    if type(n) == list:
                        rsync_acl_list.splice(h.acl_ips)
                    else:
                        rsync_acl_list.append(h.acl_ips)
        return dict(values=rsync_acl_list)

#http://mirrors.fedoraproject.org/mirrorlist?repo=core-$releasever&arch=$basearch
#http://mirrors.fedoraproject.org/mirrorlist?repo=core-debug-$releasever&arch=$basearch
    @expose(template="mirrors.templates.mirrorlist", format="plain", content_type="text/plain")
    def mirrorlist(self, repo=None, arch=None, country=None):
        pass

    @expose(template="mirrors.templates.login")
    def login(self, forward_url=None, previous_url=None, *args, **kw):

        if not identity.current.anonymous \
            and identity.was_login_attempted() \
            and not identity.get_identity_errors():
            raise redirect(forward_url)

        forward_url=None
        previous_url= cherrypy.request.path

        if identity.was_login_attempted():
            msg=_("The credentials you supplied were not correct or "
                   "did not grant access to this resource.")
        elif identity.get_identity_errors():
            msg=_("You must provide your credentials before accessing "
                   "this resmailource.")
        else:
            msg=_("Please log in.")
            forward_url= cherrypy.request.headers.get("Referer", "/")
        cherrypy.response.status=403
        return dict(message=msg, previous_url=previous_url, logging_in=True,
                    original_parameters=cherrypy.request.params,
                    forward_url=forward_url)

    @expose()
    def logout(self):
        identity.current.logout()
        raise redirect("/")
    
    @expose(template="mirrors.templates.register")
    def register(self, username="", display_name="", email_address="", tg_errors=None):
        if tg_errors:
            turbogears.flash(createErrorString(tg_errors))
            username, display_name, email_address = map(cherrypy.request.input_values.get, ["username", "display_name", "email_address"])
                    
        return dict(username=username, display_name=display_name, email_address=email_address)

    @expose()
    @error_handler(register)
    @validate(validators=my_validators.RegisterSchema)
    def doRegister(self, username, display_name, password1, password2, email_address):
        username = str(username)
        email_address = str(email_address)
        redirect_to_register = lambda:redirect("/register", {"username":username, "display_name":display_name, "email_address":email_address})
        
        try:
            User.by_user_name(username)
        except sqlobject.SQLObjectNotFound:
            pass
        else:
            turbogears.flash("Error:User %s Already Exists"%username)
            raise redirect_to_register()
        
        
        try:
            User.by_email_address(email_address)
        except sqlobject.SQLObjectNotFound:
            pass
        else:
            turbogears.flash("Error:Email-Address %s Already Exists"%username)
            raise redirect_to_register()
        
        #create user
        user = User(user_name=username, email_address=email_address, display_name=str(display_name), password=str(password1))
        
        #add user to user group
        user.addGroup(Group.by_group_name("user"))
        
        raise redirect("/")
        
