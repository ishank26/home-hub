# Share recipes from a phone

Open `/phone/` on your private Home Hub address. The mobile page accepts a recipe
link, reads a preview only when Preview is tapped, then saves to the dashboard's
server catalog only when Save is tapped. Receiving an Android share or an iPhone
shortcut link does not fetch the publisher or mutate the catalog. Saved entries
appear under Recipes → Saved. Recipe Tracker has a separate browser-local library.

On a device already paired with Home Hub, use Recipes → Share from phone → Pair
this phone → Create pairing code. Enter the six-digit code on the phone within
five minutes. Pairing grants the phone the same whole-Hub access as the tablet,
including its existing permitted controls. Codes are one-use, limited to five
attempts globally, replaced by a new code, and lost on service restart. Persistent
admission remains an HttpOnly SameSite=Strict cookie. No persistent token reaches
JavaScript or the pairing response body. The phone shell is readable on admitted
networks; catalog and controls still require the admission cookie.

Android: open the HTTPS phone page in Chrome and install Home Hub Recipes. In a
recipe app or browser, choose Share → Home Hub Recipes. The GET share target
accepts URL/title/text; only a single recognizable http(s) URL is prefilled.
The narrow service worker has no cache or API interception. Its scope is only
`/phone/`, so it does not control the tablet dashboard.

iPhone: the page gives setup instructions for a Share Sheet shortcut. Receive URLs
and Safari web pages, extract URLs from Shortcut Input, take the first URL, URL
Encode it, append that variable to the page's displayed `?url=` destination, and
Open URLs. This shortcut must be created on the owner's phone. Copy/paste works
on either phone without installation. Phones must be able to reach the private
Home Hub; native Android installation requires HTTPS. No public forwarding or
Funnel is required. A private HTTPS reverse proxy must use the LAN backend, not
loopback, so existing token admission is retained.

Limits: a recipe publisher may lack structured recipe data or block retrieval;
the preview reports that error. Timed-out writes are uncertain; check Recent or
Saved before retrying. Existing backend public-URL validation and catalog bounds
apply. Old phones without PWA share-target support can use copy/paste. Actual
native share-sheet acceptance must be verified on the owner's Android and iPhone.
