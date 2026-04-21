package org.kivy.android;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.MediaType;
import java.io.IOException;
import java.util.concurrent.TimeUnit;

/**
 * HTTP 请求辅助类，打包进 APK DEX 后天然在 app ClassLoader 上下文中，
 * 因此可以直接加载 okhttp3 类（不受 pyjnius ClassLoader 隔离影响）。
 * Python 通过 pyjnius 调用此类来发送代理请求。
 */
public class CloudHttpHelper {

    // OkHttpClient 单例（线程安全，可复用）
    private static OkHttpClient _client = null;

    private static OkHttpClient getClient() {
        if (_client == null) {
            _client = new OkHttpClient.Builder()
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(15, TimeUnit.SECONDS)
                .writeTimeout(15, TimeUnit.SECONDS)
                .followRedirects(true)
                .followSslRedirects(true)
                .build();
        }
        return _client;
    }

    /**
     * 发送 GET 请求，返回响应体字符串。
     * 失败时返回 "ERROR:" 前缀的错误信息。
     *
     * @param url 目标 URL
     * @return 响应体字符串，或 "ERROR:<message>"
     */
    public static String get(String url) {
        try {
            Request request = new Request.Builder()
                .url(url)
                .get()
                .build();

            try (Response response = getClient().newCall(request).execute()) {
                if (!response.isSuccessful()) {
                    return "ERROR:HTTP_" + response.code() + ":" + response.message();
                }
                if (response.body() == null) {
                    return "ERROR:Empty body";
                }
                return response.body().string();
            }
        } catch (IOException e) {
            return "ERROR:IOException:" + e.getMessage();
        } catch (Exception e) {
            return "ERROR:Exception:" + e.getMessage();
        }
    }

    /**
     * 发送 POST 请求（JSON），返回响应体字符串。
     *
     * @param url      目标 URL
     * @param jsonBody JSON 请求体
     * @return 响应体字符串，或 "ERROR:<message>"
     */
    public static String postJson(String url, String jsonBody) {
        try {
            Request request = new Request.Builder()
                .url(url)
                .post(Request.Body.create(jsonBody, MediaType.parse("application/json; charset=utf-8")))
                .build();

            try (Response response = getClient().newCall(request).execute()) {
                if (!response.isSuccessful()) {
                    return "ERROR:HTTP_" + response.code() + ":" + response.message();
                }
                if (response.body() == null) {
                    return "ERROR:Empty body";
                }
                return response.body().string();
            }
        } catch (IOException e) {
            return "ERROR:IOException:" + e.getMessage();
        } catch (Exception e) {
            return "ERROR:Exception:" + e.getMessage();
        }
    }
}
