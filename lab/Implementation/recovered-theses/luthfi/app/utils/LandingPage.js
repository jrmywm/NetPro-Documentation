const getHomePage = (req, res) => {
    const htmlResponse = `
          <!DOCTYPE html>
          <html lang="en">
          <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>NetPro Endpoint</title>
            <link rel="icon" href="/images/favicon.ico" type="image/x-icon">
            <style>
              * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
              }

              body {
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                background: linear-gradient(to bottom right, #EBF8FF, #BEE3F8);
              }

              .container {
                max-width: 1200px;
                width: 90%;
                margin: 2rem auto;
                background: white;
                border-radius: 1rem;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                overflow: hidden;
                display: grid;
                grid-template-columns: 1fr 1fr;
              }

              .branding {
                background: linear-gradient(to bottom right, #2B6CB0, #2C5282);
                padding: 3rem;
                color: white;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                text-align: center;
                position: relative;
              }

              .branding::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: linear-gradient(135deg, rgba(43, 108, 176, 0.9), rgba(44, 82, 130, 0.9));
                z-index: 1;
              }

              .branding-content {
                position: relative;
                z-index: 2;
              }

              .branding h1 {
                font-size: 2.5rem;
                font-weight: bold;
                margin-bottom: 1.5rem;
                letter-spacing: -0.025em;
              }

              .branding p {
                font-size: 1.125rem;
                opacity: 0.9;
                max-width: 80%;
                margin: 0 auto;
                line-height: 1.6;
              }

              .divider {
                width: 50%;
                height: 1px;
                background: rgba(255, 255, 255, 0.4);
                margin: 1.5rem auto;
              }

              .content {
                padding: 3rem;
                display: flex;
                flex-direction: column;
                justify-content: center;
              }

              .content h2 {
                color: #2B6CB0;
                font-size: 1.875rem;
                font-weight: 600;
                margin-bottom: 1rem;
                text-align: center;
              }

              .content p {
                color: #4A5568;
                text-align: center;
                margin-bottom: 2rem;
              }

              .warning {
                background: #FED7D7;
                color: #C53030;
                padding: 1rem;
                border-radius: 0.5rem;
                text-align: center;
                font-weight: 500;
              }

              @media (max-width: 768px) {
                .container {
                  grid-template-columns: 1fr;
                }
                
                .branding {
                  padding: 2rem;
                }
                
                .content {
                  padding: 2rem;
                }
              }
            </style>
          </head>
          <body>
            <div class="container">
              <div class="branding">
                <div class="branding-content">
                  <h1>NetPro</h1>
                  <p>Indonesia's premier platform for monitoring and managing illegal domains</p>
                  <div class="divider"></div>
                  <p>Join us in making Indonesia's internet safer and more secure</p>
                </div>
              </div>
              <div class="content">
                <h2>Welcome to NetPro Endpoint</h2>
                <p>This is a secure endpoint for managing domain monitoring and security operations.</p>
                <div class="warning">
                  Unauthorized access is strictly prohibited!
                </div>
              </div>
            </div>
          </body>
          </html>
      `;
    res.send(htmlResponse);
};

const getSocketTestPage = (req, res) => {
    const htmlResponse = `
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>NetPro - Socket.IO Test</title>
        <link rel="icon" href="/images/favicon.ico" type="image/x-icon">
        <script src="https://cdn.socket.io/4.7.4/socket.io.min.js"></script>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            }

            body {
                min-height: 100vh;
                background: linear-gradient(to bottom right, #EBF8FF, #BEE3F8);
                padding: 2rem;
            }

            .container {
                max-width: 1000px;
                margin: 0 auto;
                background: white;
                border-radius: 1rem;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                overflow: hidden;
            }

            .header {
                background: linear-gradient(to right, #2B6CB0, #2C5282);
                color: white;
                padding: 2rem;
                text-align: center;
            }

            .header h1 {
                font-size: 2rem;
                margin-bottom: 0.5rem;
            }

            .header p {
                opacity: 0.9;
            }

            .content {
                padding: 2rem;
            }

            .status-container {
                background: #F7FAFC;
                border-radius: 0.5rem;
                padding: 1rem;
                margin-bottom: 1rem;
                display: flex;
                align-items: center;
                gap: 1rem;
            }

            .status-indicator {
                width: 12px;
                height: 12px;
                border-radius: 50%;
                background: #E53E3E;
            }

            .status-indicator.connected {
                background: #48BB78;
            }

            .messages-container {
                background: #F7FAFC;
                border-radius: 0.5rem;
                padding: 1rem;
                max-height: 400px;
                overflow-y: auto;
            }

            .message {
                background: white;
                padding: 1rem;
                border-radius: 0.5rem;
                margin-bottom: 0.5rem;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            }

            .message:last-child {
                margin-bottom: 0;
            }

            .progress-bar {
                width: 100%;
                height: 4px;
                background: #E2E8F0;
                border-radius: 2px;
                margin-top: 0.5rem;
                overflow: hidden;
            }

            .progress-bar-fill {
                height: 100%;
                background: #4299E1;
                width: 0%;
                transition: width 0.3s ease;
            }

            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 1rem;
                margin-top: 1rem;
            }

            .stat-card {
                background: white;
                padding: 1rem;
                border-radius: 0.5rem;
                text-align: center;
            }

            .stat-card h3 {
                color: #4A5568;
                font-size: 0.875rem;
                margin-bottom: 0.5rem;
            }

            .stat-card p {
                color: #2B6CB0;
                font-size: 1.5rem;
                font-weight: 600;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>NetPro Socket.IO Test</h1>
                <p>Real-time upload progress monitoring</p>
            </div>
            <div class="content">
                <div class="status-container">
                    <div id="status-indicator" class="status-indicator"></div>
                    <div id="status-text">Connecting to server...</div>
                </div>
                <div class="messages-container" id="messages"></div>
            </div>
        </div>

        <script>
            const socket = io(); // Same origin: works through the deployed HTTPS proxy.
            const statusIndicator = document.getElementById('status-indicator');
            const statusText = document.getElementById('status-text');
            const messagesDiv = document.getElementById('messages');

            socket.on('connect', () => {
                statusIndicator.classList.add('connected');
                statusText.textContent = 'Connected to server';
                console.log('Connected to server');
            });

            socket.on('disconnect', () => {
                statusIndicator.classList.remove('connected');
                statusText.textContent = 'Disconnected from server';
                console.log('Disconnected from server');
            });

            socket.on('uploadProgress', (data) => {
                const message = document.createElement('div');
                message.className = 'message';
                
                const progress = data.progress.toFixed(2);
                const stats = \`
                    <div class="stats">
                        <div class="stat-card">
                            <h3>Progress</h3>
                            <p>\${progress}%</p>
                            <div class="progress-bar">
                                <div class="progress-bar-fill" style="width: \${progress}%"></div>
                            </div>
                        </div>
                        <div class="stat-card">
                            <h3>Processed Records</h3>
                            <p>\${data.processedRecords} / \${data.totalRecords}</p>
                        </div>
                        <div class="stat-card">
                            <h3>Unique Domains</h3>
                            <p>\${data.uniqueDomains}</p>
                        </div>
                        <div class="stat-card">
                            <h3>Duplicate Domains</h3>
                            <p>\${data.duplicateDomains}</p>
                        </div>
                    </div>
                \`;
                
                message.innerHTML = stats;
                messagesDiv.appendChild(message);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
                console.log('Upload Progress:', data);
            });

            socket.on('test', (data) => {
                const message = document.createElement('div');
                message.className = 'message';
                message.textContent = \`Test message: \${data}\`;
                messagesDiv.appendChild(message);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
                console.log('Test message:', data);
            });
        </script>
    </body>
    </html>
    `;
    res.send(htmlResponse);
};

module.exports = { getHomePage, getSocketTestPage };
