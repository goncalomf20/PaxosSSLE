import java.io.*;
import java.net.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

public class NodeServer {
    private static final int PORT = 5000;
    private static final Map<Integer, String> nodes = new ConcurrentHashMap<>();
    private static final Map<String, String[]> accounts = new ConcurrentHashMap<>();
    private static final Map<String, List<Integer>> selectedWordsCache = new ConcurrentHashMap<>();
    private static int nextNodeId = 1;

    public static void main(String[] args) {
        try (ServerSocket serverSocket = new ServerSocket(PORT)) {
            System.out.println("Server is running on port " + PORT);
            while (true) {
                Socket clientSocket = serverSocket.accept();
                new Thread(new ClientHandler(clientSocket)).start();
            }
        } catch (IOException e) {
            System.err.println("Error starting server: " + e.getMessage());
        }
    }

    static class ClientHandler implements Runnable {
        private final Socket clientSocket;

        public ClientHandler(Socket socket) {
            this.clientSocket = socket;
        }

        @Override
        public void run() {
            try (BufferedReader in = new BufferedReader(new InputStreamReader(clientSocket.getInputStream()));
                 PrintWriter out = new PrintWriter(clientSocket.getOutputStream(), true)) {

                String inputLine = in.readLine();
                if (inputLine != null) {
                    Map<String, String> request = parseJson(inputLine);
                    String action = request.get("action");

                    if ("register".equals(action)) {
                        handleRegister(request, out);
                    } else if ("verify".equals(action)) {
                        handleVerify(request, out);
                    } else if ("list_nodes".equals(action)) {
                        handleListNodes(out);
                    } else {
                        out.println("Unknown action");
                    }
                }
            } catch (IOException e) {
                System.err.println("Error handling client: " + e.getMessage());
            }
        }

        private void handleRegister(Map<String, String> request, PrintWriter out) {
            String username = request.get("username");
            String ip = request.get("ip");

            if (accounts.containsKey(username)) {
                String[] passkey = accounts.get(username);
                if (passkey.length == 16) {
                    List<Integer> selectedIndices = new Random().ints(0, 16).distinct().limit(3).boxed().toList();
                    selectedWordsCache.put(username, selectedIndices);
                    out.println("Selected indices: " + selectedIndices);
                } else {
                    out.println("Invalid passkey format for user.");
                }
            } else {
                out.println("Username not allowed to register.");
            }
        }

        private void handleVerify(Map<String, String> request, PrintWriter out) {
            String username = request.get("username");
            String sum = request.get("sum");
            String ip = request.get("ip");

            List<Integer> selectedIndices = selectedWordsCache.get(username);
            if (selectedIndices == null) {
                out.println("No words selected for this user. Register first.");
                return;
            }

            String[] passkey = accounts.get(username);
            if (passkey == null || passkey.length != 16) {
                out.println("Invalid passkey format for user.");
                return;
            }

            StringBuilder calculatedSum = new StringBuilder();
            for (int index : selectedIndices) {
                calculatedSum.append(passkey[index]);
            }

            if (calculatedSum.toString().equals(sum)) {
                int nodeId = nextNodeId++;
                nodes.put(nodeId, ip);
                out.println("Verification successful. Node ID: " + nodeId);
            } else {
                out.println("Invalid sum provided.");
            }
        }

        private void handleListNodes(PrintWriter out) {
            out.println("Nodes: " + nodes.toString());
        }

        private Map<String, String> parseJson(String jsonString) {
            Map<String, String> map = new HashMap<>();
            jsonString = jsonString.replace("{", "").replace("}", "").replace("\"", "");
            String[] pairs = jsonString.split(",");
            for (String pair : pairs) {
                String[] keyValue = pair.split(":");
                map.put(keyValue[0].trim(), keyValue[1].trim());
            }
            return map;
        }
    }
}
