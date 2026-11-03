package gl.syn.minecraft;

/** An intentional executor validation rejection, distinct from an unexpected native/mod failure. */
final class NativeActionException extends IllegalArgumentException {
    NativeActionException(String reason) {super(reason);}
}
