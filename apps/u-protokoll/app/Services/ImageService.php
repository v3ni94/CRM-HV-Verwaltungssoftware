<?php

declare(strict_types=1);

namespace App\Services;

use App\Core\Config;

/**
 * Bildverarbeitung mit GD:
 * - EXIF-Orientierung korrigieren
 * - auf konfigurierbare Maximalgröße skalieren
 * - als JPEG neu kodieren (entfernt dabei EXIF-Metadaten inkl. GPS)
 * - Thumbnail erzeugen
 */
final class ImageService
{
    public static function isImage(string $mime): bool
    {
        return in_array($mime, ['image/jpeg', 'image/png', 'image/webp'], true);
    }

    /**
     * HEIC/HEIF nach JPEG konvertieren, sofern Imagick mit HEIC-Unterstützung
     * vorhanden ist. Liefert null, wenn keine Konvertierung möglich ist.
     */
    public static function heicToJpeg(string $content): ?string
    {
        if (!class_exists(\Imagick::class)) {
            return null;
        }
        try {
            if (!in_array('HEIC', \Imagick::queryFormats('HEIC'), true)) {
                return null;
            }
            $im = new \Imagick();
            $im->readImageBlob($content);
            $im->setImageFormat('jpeg');
            $im->setImageCompressionQuality(90);
            $jpeg = $im->getImageBlob();
            $im->clear();
            return $jpeg ?: null;
        } catch (\Throwable) {
            return null;
        }
    }

    /** Pixelmaße prüfen, bevor das Bild dekodiert wird (Dekompressions-Bomben). */
    public static function dimensionsAcceptable(string $content, int $maxPixels = 50_000_000): bool
    {
        $info = @getimagesizefromstring($content);
        if ($info === false) {
            return true; // keine Bilddaten erkennbar, spätere Verarbeitung entscheidet
        }
        return ((int) $info[0] * (int) $info[1]) <= $maxPixels;
    }

    /**
     * @return array{web:string, thumb:string}|null Neu kodierte Varianten oder null,
     *         wenn das Bild nicht verarbeitet werden kann (dann Original verwenden).
     */
    public static function process(string $content, string $mime): ?array
    {
        if (!extension_loaded('gd')) {
            return null;
        }
        $img = @imagecreatefromstring($content);
        if ($img === false) {
            return null;
        }

        // EXIF-Rotation (nur JPEG trägt Orientierungsdaten)
        if ($mime === 'image/jpeg' && function_exists('exif_read_data')) {
            $exif = @exif_read_data('data://image/jpeg;base64,' . base64_encode($content));
            $orientation = (int) ($exif['Orientation'] ?? 1);
            $img = match ($orientation) {
                3 => imagerotate($img, 180, 0),
                6 => imagerotate($img, -90, 0),
                8 => imagerotate($img, 90, 0),
                default => $img,
            };
        }

        $maxSide = (int) Config::setting('upload.max_image_side', '2800');
        $quality = (int) Config::setting('upload.jpeg_quality', '82');

        $web = self::scaled($img, $maxSide);
        $thumb = self::scaled($img, 320);

        ob_start();
        imagejpeg($web, null, $quality);
        $webJpeg = (string) ob_get_clean();

        ob_start();
        imagejpeg($thumb, null, 70);
        $thumbJpeg = (string) ob_get_clean();

        imagedestroy($img);
        imagedestroy($web);
        imagedestroy($thumb);

        return ['web' => $webJpeg, 'thumb' => $thumbJpeg];
    }

    private static function scaled(\GdImage $img, int $maxSide): \GdImage
    {
        $w = imagesx($img);
        $h = imagesy($img);
        $longest = max($w, $h);
        if ($longest <= $maxSide) {
            $nw = $w;
            $nh = $h;
        } else {
            $factor = $maxSide / $longest;
            $nw = max(1, (int) round($w * $factor));
            $nh = max(1, (int) round($h * $factor));
        }
        $out = imagecreatetruecolor($nw, $nh);
        imagefill($out, 0, 0, imagecolorallocate($out, 255, 255, 255));
        imagecopyresampled($out, $img, 0, 0, 0, 0, $nw, $nh, $w, $h);
        return $out;
    }
}
