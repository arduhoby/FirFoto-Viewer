import 'package:firfoto_viewer/src/viewer/viewer_shell.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('negative EV reduces gain', () {
    expect(exposureGainForEv(-1.0), lessThan(1.0));
    expect(exposureGainForEv(-0.5), lessThan(1.0));
    expect(exposureGainForEv(0.0), 1.0);
  });

  test('positive and negative EV are reciprocal around zero', () {
    final positive = exposureGainForEv(1.0);
    final negative = exposureGainForEv(-1.0);

    expect(positive, closeTo(2.0, 0.0001));
    expect(negative, closeTo(0.5, 0.0001));
  });
}
