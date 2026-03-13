import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.flows import FlowHandler
from src.services import WhatsAppService

class TestMediaProcessing(unittest.TestCase):

    @patch('src.services.WhatsAppService.get_media_url')
    @patch('src.services.WhatsAppService.download_media_file')
    @patch('src.services.WhatsAppService.upload_to_supabase_storage')
    @patch('src.flows.log_message')
    @patch('src.flows.get_user_state')
    def test_image_reception(self, mock_get_state, mock_log, mock_upload, mock_download, mock_get_url):
        # Setup
        mock_get_state.return_value = "active"
        mock_get_url.return_value = "https://meta.com/temp_url"
        mock_download.return_value = True
        mock_upload.return_value = None # Fallback to offline path behavior for test
        
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "573001234567",
                            "id": "msg_123",
                            "type": "image",
                            "image": {
                                "id": "media_456",
                                "mime_type": "image/jpeg"
                            }
                        }]
                    }
                }]
            }]
        }
        
        # Execute
        FlowHandler.handle_incoming_message(payload)
        
        # Verify
        mock_get_url.assert_called_with("media_456")
        mock_download.assert_called()
        # Check if log_message was called with the relative path
        expected_path = "/static/uploads/573001234567/media_456.jpeg"
        mock_log.assert_any_call("573001234567", "inbound", expected_path, "image")

    @patch('src.services.WhatsAppService.get_media_url')
    @patch('src.services.WhatsAppService.download_media_file')
    @patch('src.services.WhatsAppService.upload_to_supabase_storage')
    @patch('src.flows.log_message')
    @patch('src.flows.get_user_state')
    def test_document_reception(self, mock_get_state, mock_log, mock_upload, mock_download, mock_get_url):
        # Setup
        mock_get_state.return_value = "active"
        mock_get_url.return_value = "https://meta.com/temp_url_doc"
        mock_download.return_value = True
        mock_upload.return_value = "https://mock-supabase.co/storage/v1/object/public/media/573001234567/contrato.pdf"
        
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "573001234567",
                            "id": "msg_doc_1",
                            "type": "document",
                            "document": {
                                "id": "doc_789",
                                "filename": "contrato.pdf",
                                "mime_type": "application/pdf"
                            }
                        }]
                    }
                }]
            }]
        }
        
        # Execute
        FlowHandler.handle_incoming_message(payload)
        
        # Verify
        mock_get_url.assert_called_with("doc_789")
        mock_download.assert_called()
        expected_path = "https://mock-supabase.co/storage/v1/object/public/media/573001234567/contrato.pdf"
        mock_log.assert_any_call("573001234567", "inbound", expected_path, "document")

if __name__ == '__main__':
    unittest.main()
