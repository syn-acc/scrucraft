package gl.syn.minecraft;

/** Endpoint configuration must never turn the private body bridge into an outbound credential leak. */
public final class BodyStreamEndpointTest {
    public static void main(String[] args) {
        BodyGrantTest.check();
        int checks=0;
        for(String allowed:new String[]{"ws://127.0.0.1:8769/internal/body","ws://127.0.0.1:18769/internal/body"}) {
            if(!BodyStream.loopbackEndpoint(allowed).toString().equals(allowed))throw new AssertionError(allowed);
            checks++;
        }
        for(String denied:new String[]{"wss://127.0.0.1:8769/internal/body","ws://example.com:8769/internal/body",
            "ws://127.0.0.2:8769/internal/body","ws://user:secret@127.0.0.1:8769/internal/body",
            "ws://127.0.0.1:8769/internal/body?token=bad","ws://127.0.0.1:8769/internal/body#bad",
            "ws://127.0.0.1:8769/other","ws://127.0.0.1:0/internal/body","ws://127.0.0.1/internal/body"}) {
            try{BodyStream.loopbackEndpoint(denied);throw new AssertionError("accepted "+denied);}
            catch(IllegalArgumentException expected){checks++;}
        }
        System.out.println("BodyStream endpoint checks: "+checks);
    }
}
