// ws-test.js
const WebSocket = require('ws');
const ws = new WebSocket('ws://localhost:8000/ws');

ws.on('open', function open() {
  console.log('WebSocket connection opened');
  ws.send('ping');
});

ws.on('message', function message(data) {
  console.log('Received:', data);
});

ws.on('close', function close() {
  console.log('WebSocket connection closed');
});

ws.on('error', function error(err) {
  console.error('WebSocket error:', err);
});