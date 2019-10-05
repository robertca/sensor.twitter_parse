"""Support for getting tweets from a user twitter timeline."""
import logging
import tweepy

import voluptuous as vol
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
from datetime import timedelta
from datetime import datetime
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.components.rest.sensor import RestData
from homeassistant.const import (
    CONF_NAME,
    CONF_RESOURCE,
    CONF_ACCESS_TOKEN,
    CONF_UNIT_OF_MEASUREMENT,
    CONF_VALUE_TEMPLATE,
    CONF_SCAN_INTERVAL
)
from homeassistant.helpers.entity import Entity
from homeassistant.exceptions import PlatformNotReady
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

CONF_TWITTER_KEY = 'twitter_key'
CONF_TWITTER_SECRET = 'twitter_secret'
CONF_ACCESS_SECRET = 'access_secret'
CONF_TIMELINE_ENTRIES = 'twitter_timeline_entries'
#SCAN_INTERVAL = timedelta(seconds=600)
DEFAULT_NAME = "Twitter Parse"
DOMAIN = "twitter_parse"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_RESOURCE): cv.string,
        vol.Required(CONF_ACCESS_TOKEN): cv.string,
        vol.Required(CONF_TWITTER_KEY, default=''): cv.string,
        vol.Required(CONF_TWITTER_SECRET, default=''): cv.string,
        vol.Required(CONF_ACCESS_SECRET, default=''): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_UNIT_OF_MEASUREMENT): cv.string,
        vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
        #vol.Optional(CONF_SCAN_INTERVAL, default=SCAN_INTERVAL): cv.time_period,
        vol.Optional(CONF_TIMELINE_ENTRIES, default=4): cv.positive_int
    }
)

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Twitter Parse sensor."""
    name = config.get(CONF_NAME)
    resource = config.get(CONF_RESOURCE)

    consumer_key = config.get(CONF_TWITTER_KEY)
    consumer_secret = config.get(CONF_TWITTER_SECRET)
    access_token = config.get(CONF_ACCESS_TOKEN)
    access_secret = config.get(CONF_ACCESS_SECRET)
    unit = config.get(CONF_UNIT_OF_MEASUREMENT)
    timeline_entries = config.get(CONF_TIMELINE_ENTRIES)

    value_template = config.get(CONF_VALUE_TEMPLATE)
    if value_template is not None:
        value_template.hass = hass

    if consumer_key and consumer_secret:
        auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        auth.set_access_token(access_token, access_secret)
    else:
        auth = None
    
    if auth is None:
        raise PlatformNotReady

    api = tweepy.API(auth)

    add_entities(
        [TwitterParseSensor(hass, api, name, resource, timeline_entries, value_template, unit)], True
    )

class TwitterParseSensor(Entity):
    """Representation of a Twitter Parse sensor."""

    def __init__(self, hass, api, name, twitter_user, num_timeline_entries, value_template, unit):
        """Initialize Twitter Parse sensor."""
        self.hass = hass
        self.api = api
        self._name = name
        self._state = None
        self._value_template = value_template
        self._unit_of_measurement = unit
        self.timeline = []
        self.twitter_user = twitter_user
        # hardcoded for now to avoid rate limiting
        self.num_timeline_entries = min(30, num_timeline_entries)

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return self._unit_of_measurement

    @property
    def state(self):
        """Return the state of the device."""
        return self._state


    @property
    def state_attributes(self):
        """Return the optional state attributes."""
        data = {
            'timeline': self.timeline,
            'last_update': datetime.now()
        }
        return data

    def process_status(self, twitter_status):
        return {
            "text": twitter_status.text,
            "url": "https://twitter.com/%s/status/%s" % (twitter_status.user.screen_name, twitter_status.id),
            "posted_at": twitter_status.created_at
        }

    def update(self):
        """Get the latest data from the source and update the state."""

        user = self.api.get_user(self.twitter_user)
        if (user == None):
            _LOGGER.error("Unable to retrieve data from twitter api")
            return

        try:
            self.timeline = []

            # Iterate through the first N statuses in the home timeline
            for status in tweepy.Cursor(self.api.user_timeline, id=self.twitter_user).items(self.num_timeline_entries):
                processed_status = self.process_status(status)
                
                if self._value_template is not None:
                    processed_status["text"] = self._value_template.render_with_possible_json_value(processed_status["text"], None)

                self.timeline.append(processed_status)

            if len(self.timeline) > 0:
                self._state = self.timeline[0]["text"][0:252]
        except tweepy.RateLimitError:
            _LOGGER.error("Unable to parse data due to Twitter Rate Limiting")
            return
        except tweepy.TweepError:
            _LOGGER.error("Unable to parse data due to API Error")
            return
        except Exception as e:
            _LOGGER.error("Unable to extract data from Twitter: " + str(e))
            return
