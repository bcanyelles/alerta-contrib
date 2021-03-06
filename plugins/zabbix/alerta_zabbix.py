
import os
import logging

from alerta.app import app
from alerta.plugins import PluginBase

from pyzabbix import ZabbixAPI, ZabbixAPIException

LOG = logging.getLogger('alerta.plugins.zabbix')

ZABBIX_API_URL = os.environ.get('ZABBIX_API_URL') or app.config['ZABBIX_API_URL']
ZABBIX_USER = os.environ.get('ZABBIX_USER') or app.config['ZABBIX_USER']
ZABBIX_PASSWORD = os.environ.get('ZABBIX_PASSWORD') or app.config['ZABBIX_PASSWORD']

NO_ACTION = 0
ACTION_CLOSE = 1


class ZabbixEventAck(PluginBase):

    def __init__(self, name=None):

        self.zapi = ZabbixAPI(ZABBIX_API_URL)

        super(ZabbixEventAck, self).__init__(name)

    def pre_receive(self, alert):
        return alert

    def post_receive(self, alert):
        return

    def status_change(self, alert, status, text):

        self.zapi.login(ZABBIX_USER, ZABBIX_PASSWORD)

        if alert.event_type != 'zabbixAlert':
            return

        if alert.status == status or not status in ['ack', 'closed']:
            return

        trigger_id = alert.attributes.get('triggerId', None)
        event_id = alert.attributes.get('eventId', None)

        if not event_id:
            LOG.error('Zabbix: eventId missing from alert attributes')
            return

        LOG.debug('Zabbix: acknowledge (%s) event=%s, resource=%s (triggerId=%s, eventId=%s) ', status, alert.event, alert.resource, trigger_id, event_id)

        if status == 'ack':
            try:
                r = self.zapi.event.get(objectids=trigger_id, acknowledged=False, output='extend', sortfield='clock', sortorder='DESC', limit=10)
                event_ids = [e['eventid'] for e in r]
            except ZabbixAPIException:
                event_ids = None

            LOG.debug('Zabbix: status=ack; triggerId %s => eventIds %s', trigger_id, ','.join(event_ids))

            try:
                LOG.debug('Zabbix: ack all events for trigger...')
                r = self.zapi.event.acknowledge(eventids=event_ids, message='%s: %s' % (status, text), action=NO_ACTION)
            except ZabbixAPIException:
                try:
                    LOG.debug('Zabbix: ack all failed, ack only the one event')
                    r = self.zapi.event.acknowledge(eventids=event_id, message='%s: %s' % (status, text), action=NO_ACTION)
                except ZabbixAPIException as e:
                    raise RuntimeError("Zabbix: ERROR - %s", e)

            LOG.debug('Zabbix: event.acknowledge(ack) => %s', r)
            text = text + ' (acknowledged in Zabbix)'

        elif status == 'closed':

            try:
                r = self.zapi.event.get(objectids=trigger_id, acknowledged=True, output='extend', sortfield='clock', sortorder='DESC', limit=10)
                event_ids = [e['eventid'] for e in r]
            except ZabbixAPIException:
                event_ids = None

            LOG.debug('Zabbix: status=closed; triggerId %s => eventIds %s', trigger_id, ','.join(event_ids))

            try:
                LOG.debug('Zabbix: close all events for trigger...')
                r = self.zapi.event.acknowledge(eventids=event_ids, message='%s: %s' % (status, text), action=ACTION_CLOSE)
            except ZabbixAPIException:
                try:
                    LOG.debug('Zabbix: ack all failed, close only the one event')
                    r = self.zapi.event.acknowledge(eventids=event_id, message='%s: %s' % (status, text), action=ACTION_CLOSE)
                except ZabbixAPIException as e:
                    raise RuntimeError("Zabbix: ERROR - %s", e)

            LOG.debug('Zabbix: event.acknowledge(closed) => %s', r)
            text = text + ' (closed in Zabbix)'

        return alert, status, text
