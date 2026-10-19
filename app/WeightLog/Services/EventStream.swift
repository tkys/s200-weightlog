import Foundation

struct ServerSentEvent: Equatable, Sendable {
    let event: String
    let data: String
}

/// Minimal SSE line parser for the daemon's stream.
///
/// `URLSession.AsyncBytes.lines` drops blank lines, so instead of dispatching on
/// the blank separator we dispatch on each `data:` line. The daemon always sends
/// single-line JSON payloads, which makes that equivalent.
struct SSEParser {
    private var event: String?

    mutating func feed(_ line: String) -> ServerSentEvent? {
        if line.isEmpty || line.hasPrefix(":") {
            if line.isEmpty { event = nil }
            return nil
        }
        if let value = Self.value(of: "event", in: line) {
            event = value
            return nil
        }
        if let value = Self.value(of: "data", in: line) {
            defer { event = nil }
            return ServerSentEvent(event: event ?? "message", data: value)
        }
        return nil
    }

    private static func value(of field: String, in line: String) -> String? {
        guard line.hasPrefix(field + ":") else { return nil }
        let rest = line.dropFirst(field.count + 1)
        return String(rest.first == " " ? rest.dropFirst() : rest)
    }
}

enum StreamEvent: Sendable {
    case connected
    case disconnected
    case reading(ReadingEvent)
    case changed(Summary)
}

/// Long-lived connection to `/api/stream` that reconnects with backoff.
struct EventStream: Sendable {
    let api: APIClient

    func events() -> AsyncStream<StreamEvent> {
        AsyncStream { continuation in
            let task = Task {
                var backoff: Double = 1
                while !Task.isCancelled {
                    do {
                        var req = URLRequest(url: api.baseURL.appending(path: "api/stream"))
                        req.timeoutInterval = 60  // daemon pings every 15 s
                        let (bytes, response) = try await api.session.bytes(for: req)
                        guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                            throw URLError(.badServerResponse)
                        }
                        continuation.yield(.connected)
                        backoff = 1
                        var parser = SSEParser()
                        for try await line in bytes.lines {
                            if let sse = parser.feed(line), let event = Self.decode(sse) {
                                continuation.yield(event)
                            }
                        }
                    } catch {
                        // fall through to reconnect
                    }
                    continuation.yield(.disconnected)
                    try? await Task.sleep(for: .seconds(backoff))
                    backoff = min(backoff * 2, 30)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    static func decode(_ sse: ServerSentEvent) -> StreamEvent? {
        let data = Data(sse.data.utf8)
        let decoder = WireCoding.decoder()
        switch sse.event {
        case "reading":
            return (try? decoder.decode(ReadingEvent.self, from: data)).map(StreamEvent.reading)
        case "changed":
            return (try? decoder.decode(ChangedEvent.self, from: data)).map { .changed($0.summary) }
        default:
            return nil
        }
    }
}
