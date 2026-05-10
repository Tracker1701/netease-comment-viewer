package org.kivy.android;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * 使用 Android 内置 HttpURLConnection 发送 HTTP/HTTPS 请求。
 * Python 通过 pyjnius 调用此类，绕过 Python 的 DNS / SSL 限制。
 */
public class CloudHttpHelper {

    private static final int CONNECT_TIMEOUT_MS = 15000;
    private static final int READ_TIMEOUT_MS    = 15000;

    private static final String USER_AGENT =
        "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 " +
        "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36";

    /**
     * 发送 GET 请求，返回响应体字符串。
     * 失败时返回 "ERROR:<message>"。
     */
    public static String get(String urlStr) {
        HttpURLConnection conn = null;
        try {
            URL url = new URL(urlStr);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(CONNECT_TIMEOUT_MS);
            conn.setReadTimeout(READ_TIMEOUT_MS);
            conn.setRequestProperty("User-Agent", USER_AGENT);
            conn.setRequestProperty("Referer", "https://music.163.com/");
            conn.setInstanceFollowRedirects(true);

            int code = conn.getResponseCode();
            if (code < 200 || code >= 300) {
                return "ERROR:HTTP_" + code + ":" + conn.getResponseMessage();
            }
            return readStream(conn);
        } catch (IOException e) {
            return "ERROR:IOException:" + e.getMessage();
        } catch (Exception e) {
            return "ERROR:Exception:" + e.getMessage();
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    /**
     * 发送 POST 请求（JSON），返回响应体字符串。
     * 失败时返回 "ERROR:<message>"。
     */
    public static String postJson(String urlStr, String jsonBody) {
        HttpURLConnection conn = null;
        try {
            URL url = new URL(urlStr);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(CONNECT_TIMEOUT_MS);
            conn.setReadTimeout(READ_TIMEOUT_MS);
            conn.setRequestProperty("User-Agent", USER_AGENT);
            conn.setRequestProperty("Referer", "https://music.163.com/");
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            conn.setDoOutput(true);
            conn.setInstanceFollowRedirects(true);

            byte[] bytes = jsonBody.getBytes(StandardCharsets.UTF_8);
            conn.setRequestProperty("Content-Length", String.valueOf(bytes.length));
            try (OutputStream os = conn.getOutputStream()) {
                os.write(bytes);
            }

            int code = conn.getResponseCode();
            if (code < 200 || code >= 300) {
                return "ERROR:HTTP_" + code + ":" + conn.getResponseMessage();
            }
            return readStream(conn);
        } catch (IOException e) {
            return "ERROR:IOException:" + e.getMessage();
        } catch (Exception e) {
            return "ERROR:Exception:" + e.getMessage();
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    private static String readStream(HttpURLConnection conn) throws IOException {
        BufferedReader reader = new BufferedReader(
            new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8)
        );
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) {
            sb.append(line);
        }
        reader.close();
        return sb.toString();
    }
}
