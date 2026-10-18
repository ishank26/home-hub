import json
import socket
import unittest
from unittest.mock import patch, Mock
import recipes

RECIPE = {'@type': 'Recipe', 'name': 'Simple tomato pasta',
          'recipeIngredient': ['2 cups pasta', '<b>3</b> tomatoes'],
          'recipeInstructions': [{'@type':'HowToSection','itemListElement':[
              {'@type':'HowToStep','text':'Boil the pasta.'}, {'text':'Stir in tomatoes.'}]}]}

def page(recipe):
    return '<script type="application/ld+json">'+json.dumps({'@graph':[recipe]})+'</script>'

class RecipeTests(unittest.TestCase):
    def test_jsonld_graph_sections_and_text_only_output(self):
        recipe = recipes.parse_recipe(page(RECIPE), 'https://example.com/pasta')
        self.assertEqual(recipe['ingredients'], ['2 cups pasta', '3 tomatoes'])
        self.assertEqual(recipe['steps'], ['Boil the pasta.', 'Stir in tomatoes.'])
        self.assertNotIn('<b>', str(recipe))
        self.assertEqual(recipe['url'], 'https://example.com/pasta')

    def test_refuses_non_recipe_and_malformed_metadata(self):
        for source in ['<script>alert(1)</script>', '<script type="application/ld+json">bad</script>', page({'@type':'Article'})]:
            with self.assertRaisesRegex(ValueError,'No structured recipe'):recipes.parse_recipe(source,'https://example.com')

    def test_url_refuses_internal_credentials_ports_and_protocols(self):
        for url in ['http://example.com', 'https://127.0.0.1', 'https://[::1]', 'https://192.168.0.1',
                    'https://169.254.169.254/latest', 'https://' + 'user:secret@example.com',
                    'https://example.com:8123', 'file:///etc/passwd', 'https://localhost',
                    'https://example.com\\@127.0.0.1', 'https://[::ffff:8.8.8.8]', 'https://example.com/\n']:
            with self.assertRaises(ValueError,msg=url):recipes.safe_url(url)
        self.assertEqual(recipes.safe_url('https://example.com/a?q=b#fragment'),'https://example.com/a?q=b')

    def test_dns_rejects_any_private_answer_and_pins_public_socket(self):
        records=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.215.14',443))]
        with patch.object(recipes.socket,'getaddrinfo',return_value=records):
            self.assertEqual(recipes.public_addresses('example.com'),records)
        records.append((socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443)))
        with patch.object(recipes.socket,'getaddrinfo',return_value=records):
            with self.assertRaises(ValueError):recipes.public_addresses('example.com')
        record=records[0]
        with patch.object(recipes.socket,'socket') as socket_factory:
            conn=recipes.PinnedHTTPS('example.com',record,1)
            conn._context=Mock();conn.connect()
            socket_factory.return_value.connect.assert_called_once_with(record[4])
            self.assertEqual(conn._context.wrap_socket.call_args.kwargs['server_hostname'],'example.com')

    def test_redirect_to_internal_address_refused_before_connection(self):
        response=Mock(status=302);response.getheader.return_value='https://127.0.0.1/private'
        with patch.object(recipes,'public_addresses',return_value=[Mock()]),patch.object(recipes,'PinnedHTTPS') as connection:
            connection.return_value.getresponse.return_value=response
            with self.assertRaises(ValueError):recipes.fetch_html('https://example.com/recipe')
            self.assertEqual(connection.call_count,1)

    def test_fetch_bounds_and_no_cookie_or_auth_forwarding(self):
        response=Mock(status=200)
        response.getheader.side_effect=lambda name,default='': {'Content-Type':'text/html','Content-Encoding':'identity'}.get(name,default)
        response.headers.get_content_charset.return_value='utf-8'
        response.read1.side_effect=[page(RECIPE).encode(),b'']
        with patch.object(recipes,'public_addresses',return_value=[Mock()]),patch.object(recipes,'PinnedHTTPS') as connection:
            connection.return_value.getresponse.return_value=response
            result=recipes.read_recipe('https://example.com/recipe')
            self.assertEqual(result['title'],'Simple tomato pasta')
            headers=connection.return_value.request.call_args.kwargs['headers']
            self.assertNotIn('Cookie',headers);self.assertNotIn('Authorization',headers)
        response.read1.side_effect=[b'x'*100,b'']
        with patch.object(recipes,'MAX_HTML',50),patch.object(recipes,'public_addresses',return_value=[Mock()]),patch.object(recipes,'PinnedHTTPS') as connection:
            connection.return_value.getresponse.return_value=response
            with self.assertRaisesRegex(ValueError,'too large'):recipes.fetch_html('https://example.com/recipe')

    def test_hard_deadline_interrupts_slow_headers_and_body_and_releases_slots(self):
        import threading
        import time
        for stage in ('headers', 'body'):
            released = threading.Event()
            response=Mock(status=200)
            response.getheader.side_effect=lambda name,default='': {'Content-Type':'text/html','Content-Encoding':'identity'}.get(name,default)
            response.headers.get_content_charset.return_value='utf-8'
            def blocked():
                released.wait(1)
                raise OSError('synthetic slow publisher')
            conn=Mock()
            conn.abort.side_effect=released.set
            if stage=='headers':conn.getresponse.side_effect=blocked
            else:
                conn.getresponse.return_value=response
                response.read1.side_effect=lambda size:blocked()
            with patch.object(recipes,'FETCH_SECONDS',.05),patch.object(recipes,'public_addresses',return_value=[Mock()]),patch.object(recipes,'PinnedHTTPS',return_value=conn):
                start=time.monotonic()
                with self.assertRaises(recipes.SourceUnavailable):recipes.fetch_html('https://example.com/recipe')
                self.assertLess(time.monotonic()-start,.4)
                conn.abort.assert_called_once()
        self.assertTrue(recipes._FETCHES.acquire(blocking=False))
        self.assertTrue(recipes._FETCHES.acquire(blocking=False))
        recipes._FETCHES.release();recipes._FETCHES.release()

    def test_real_socket_dripping_headers_is_interrupted(self):
        import socketserver
        import threading
        import time
        class Slow(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.recv(4096)
                try:
                    for byte in b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 100\r\n\r\n':
                        self.request.sendall(bytes([byte]));time.sleep(.01)
                except OSError:pass
        class TestTLS:
            def __init__(self,sock):self.sock=sock
            def __getattr__(self,name):return getattr(self.sock,name)
            def do_handshake(self):pass
        context=Mock();context.wrap_socket.side_effect=lambda sock,**kw:TestTLS(sock)
        http=socketserver.TCPServer(('127.0.0.1',0),Slow)
        worker=threading.Thread(target=http.handle_request);worker.start()
        record=(socket.AF_INET,socket.SOCK_STREAM,6,'',http.server_address)
        try:
            with patch.object(recipes,'FETCH_SECONDS',.12),patch.object(recipes,'public_addresses',return_value=[record]),patch.object(recipes.ssl,'create_default_context',return_value=context):
                start=time.monotonic()
                with self.assertRaises(recipes.SourceUnavailable):recipes.fetch_html('https://example.com/recipe')
                self.assertLess(time.monotonic()-start,.5)
        finally:
            http.server_close();worker.join(1)
        self.assertFalse(worker.is_alive())
