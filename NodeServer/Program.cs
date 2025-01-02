using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

class NodeServer
{
    private static readonly int HttpPort = 5000;
    private static readonly int SocketPort = 23843;
    private static readonly ConcurrentDictionary<int, string> Nodes = new();
    private static readonly ConcurrentDictionary<string, string[]> Accounts = new();
    private static readonly ConcurrentDictionary<string, List<int>> SelectedWordsCache = new();
    private static readonly ConcurrentDictionary<string, string> Expire = new();
    private static int NextNodeId = 1;

    static async Task Main(string[] args)
    {
        // Start the socket server on a separate thread
        Thread socketThread = new Thread(StartSocketServer) { IsBackground = true };
        socketThread.Start();

        // Start the HTTP server
        Console.WriteLine($"HTTP server running on 10.0.2.15:{HttpPort}");
        HttpListener listener = new HttpListener();
        listener.Prefixes.Add($"http://10.0.2.15:{HttpPort}/");
        listener.Start();

        while (true)
        {
            var context = await listener.GetContextAsync();
            HandleHttpRequest(context);
        }
    }

    private static void HandleHttpRequest(HttpListenerContext context)
    {
        try
        {
            var request = context.Request;
            var response = context.Response;

            using var reader = new StreamReader(request.InputStream, request.ContentEncoding);
            string jsonData = reader.ReadToEnd();
            var requestData = JsonSerializer.Deserialize<Dictionary<string, object>>(jsonData);

            string path = request.Url.AbsolutePath.Trim('/');
            string method = request.HttpMethod;

            if (method == "POST" && path.Contains("/verify"))
            {
                string username = path.Split('/')[0];
                HandleVerify(context, username, requestData);
            }
            else if (method == "POST")
            {
                string username = path.Split('/')[0];
                HandleRegister(context, username, requestData);
            }
            else if (method == "GET" && path == "nodes")
            {
                HandleListNodes(context);
            }
            else
            {
                WriteResponse(response, 404, "Endpoint not found");
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error handling request: {ex.Message}");
        }
    }

    private static void HandleRegister(HttpListenerContext context, string username, Dictionary<string, object> requestData)
    {
        var response = context.Response;
        if (!requestData.TryGetValue("ip", out var ipAddressObj) || ipAddressObj is not string ipAddress)
        {
            WriteResponse(response, 400, "IP address is required");
            return;
        }

        if (Accounts.TryGetValue(username, out var passkey) && passkey.Length == 16)
        {
            var random = new Random();
            var selectedIndices = new List<int>();
            while (selectedIndices.Count < 3)
            {
                int index = random.Next(0, 16);
                if (!selectedIndices.Contains(index))
                {
                    selectedIndices.Add(index);
                }
            }
            SelectedWordsCache[username] = selectedIndices;
            WriteResponse(response, 201, new { selected_indices = selectedIndices });
        }
        else
        {
            WriteResponse(response, 400, "Username not allowed to register or invalid passkey format");
        }
    }

    private static void HandleVerify(HttpListenerContext context, string username, Dictionary<string, object> requestData)
    {
        var response = context.Response;
        if (!SelectedWordsCache.TryGetValue(username, out var selectedIndices))
        {
            WriteResponse(response, 400, "No words selected for this user. Register first.");
            return;
        }

        if (!requestData.TryGetValue("sum", out var sumObj) || sumObj is not string userSum ||
            !requestData.TryGetValue("ip", out var ipAddressObj) || ipAddressObj is not string ipAddress)
        {
            WriteResponse(response, 400, "Invalid request format");
            return;
        }

        if (!Accounts.TryGetValue(username, out var passkey) || passkey.Length != 16)
        {
            WriteResponse(response, 400, "Invalid passkey format for this user");
            return;
        }

        var calculatedSum = new StringBuilder();
        foreach (var index in selectedIndices)
        {
            calculatedSum.Append(passkey[index]);
        }

        if (calculatedSum.ToString() == userSum)
        {
            int nodeId = NextNodeId++;
            Nodes[nodeId] = ipAddress;
            WriteResponse(response, 201, new { nID = nodeId, nodes = Nodes, port = HttpPort });
        }
        else
        {
            WriteResponse(response, 400, "Invalid sum provided");
        }
    }

    private static void HandleListNodes(HttpListenerContext context)
    {
        WriteResponse(context.Response, 200, Nodes);
    }

    private static void WriteResponse(HttpListenerResponse response, int statusCode, object content)
    {
        response.StatusCode = statusCode;
        response.ContentType = "application/json";
        using var writer = new StreamWriter(response.OutputStream);
        writer.Write(JsonSerializer.Serialize(content));
    }

private static void StartSocketServer()
{
    var server = new TcpListener(IPAddress.Parse("10.0.2.15"), SocketPort);
    server.Start();
    Console.WriteLine($"Socket server running on 10.0.2.15:{SocketPort}");

    while (true)
    {
        try
        {
            var client = server.AcceptTcpClient();
            Console.WriteLine("New client connection accepted.");

            // Start handling the client in a new thread
            ThreadPool.QueueUserWorkItem(HandleSocketClient, client);
        }
        catch (SocketException ex)
        {
            Console.WriteLine($"Error accepting client connection: {ex.Message}");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Unexpected error in socket server: {ex.Message}");
        }
    }
}

private static void HandleSocketClient(object obj)
{
    var client = (TcpClient)obj;

    try
    {
        // Configure timeouts for socket operations
        client.ReceiveTimeout = 10000; // 10 seconds
        client.SendTimeout = 10000;    // 10 seconds

        using var stream = client.GetStream();
        using var reader = new StreamReader(stream, Encoding.UTF8);
        using var writer = new StreamWriter(stream, Encoding.UTF8) { AutoFlush = true };

        // Log client connection
        Console.WriteLine($"Client connected: {client.Client.RemoteEndPoint}");

        // Read input
        string input = reader.ReadLine();
        if (string.IsNullOrEmpty(input))
        {
            Console.WriteLine("Client disconnected or sent empty input.");
            return;
        }

        // Log received data
        Console.WriteLine($"Received: {input}");

        // Parse input data
        var data = JsonSerializer.Deserialize<Dictionary<string, object>>(input);
        if (data.TryGetValue("username", out var usernameObj) &&
            data.TryGetValue("passkey", out var passkeyObj) &&
            usernameObj is string username &&
            passkeyObj is string passkey)
        {
            var passkeyArray = passkey.Split(' ');
            if (passkeyArray.Length == 16)
            {
                Accounts[username] = passkeyArray;

                if (client.Connected)
                {
                    writer.WriteLine("Passkey received and stored");
                }
                else
                {
                    Console.WriteLine("Client disconnected before the server could respond.");
                }
            }
            else
            {
                if (client.Connected)
                {
                    writer.WriteLine("Invalid passkey format. Must contain 16 words.");
                }
            }
        }
        else
        {
            if (client.Connected)
            {
                writer.WriteLine("Invalid data format. Expected username and passkey.");
            }
        }
    }
    catch (IOException ioEx)
    {
        Console.WriteLine($"Socket I/O error: {ioEx.Message}");
    }
    catch (ObjectDisposedException ex)
    {
        Console.WriteLine($"Socket closed unexpectedly: {ex.Message}");
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Unexpected error handling client: {ex.Message}");
    }
    finally
    {
        if (client.Connected)
        {
            Console.WriteLine($"Client disconnected: {client.Client.RemoteEndPoint}");
        }
        client.Close();
    }
}
}
